"""编排器.

将解析、提取、验证、分析、总结五个阶段串联为完整流水线.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..models.paper import (
    Paper, Claim, Experiment, Methodology, ValidationResult, Limitation, AnalysisReport,
    CLAIM_TYPE_ZH, LIMITATION_CATEGORY_ZH, SEVERITY_ZH, VERDICT_ZH,
)
from ..parser.parser import PaperParser
from ..extractor.extractor import ClaimExtractor
from ..validator.validator import ClaimValidator
from ..analyzer.analyzer import LimitationAnalyzer
from ..summarizer.summarizer import PaperSummarizer
from ..llm.client import LLMClient

# 进度回调签名: (phase, step, detail, elapsed_ms)
ProgressCallback = Callable[[str, str, str, float], None] | None


def _noop(phase: str, step: str, detail: str, elapsed: float) -> None:
    pass


@dataclass
class PipelineState:
    """流水线共享状态."""
    paper_path: str
    paper: Paper | None = None
    methodologies: list[Methodology] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    experiments: list[Experiment] = field(default_factory=list)
    validations: list[ValidationResult] = field(default_factory=list)
    limitations: list[Limitation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class PaperAgent:
    """论文分析 Agent.

    用法:
        agent = PaperAgent()
        report = agent.analyze("path/to/paper.pdf", on_progress=my_callback)
    """

    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        skip_validation: bool = False,
        config_path: str = "config.yaml",
    ) -> None:
        self.llm = llm or LLMClient(config_path=config_path)
        self.parser = PaperParser(llm=self.llm)
        self.extractor = ClaimExtractor(llm=self.llm)
        self.validator = ClaimValidator(llm=self.llm, sandbox=None)  # sandbox 延迟初始化
        self.analyzer = LimitationAnalyzer(llm=self.llm)
        self.summarizer = PaperSummarizer(llm=self.llm)
        self.skip_validation = skip_validation

    def analyze(
        self,
        paper_path: str | Path,
        on_progress: ProgressCallback = None,
    ) -> AnalysisReport:
        """完整分析流水线."""
        progress = on_progress or _noop
        state = PipelineState(paper_path=str(paper_path))
        t0 = time.time()

        def _elapsed() -> float:
            return time.time() - t0

        # Phase 1: 解析 PDF
        progress("parse", "start", "启动 PDF 解析...", _elapsed())
        self._phase_parse(state, progress, _elapsed)

        # Phase 2: 提取方法论与观点
        progress("extract", "start", "构建 prompt，准备调用 LLM...", _elapsed())
        self._phase_extract(state, progress, _elapsed)

        # Phase 3: 验证（可选）
        if not self.skip_validation:
            n_claims = len(state.claims)
            progress("validate", "start", f"准备验证 {n_claims} 条观点", _elapsed())
            self._phase_validate(state, progress, _elapsed)
        else:
            progress("validate", "skip", "已跳过", _elapsed())

        # Phase 4: 局限性分析
        progress("analyze", "start", "构建局限性分析 prompt...", _elapsed())
        self._phase_analyze(state, progress, _elapsed)

        # Phase 5: 总结（独立 Summarizer agent）
        progress("summarize", "start", "Summarizer 生成每 claim 摘要 + 整体总结...", _elapsed())
        self._phase_summarize(state, progress, _elapsed)

        # 生成报告
        progress("report", "start", "渲染 Markdown + JSON...", _elapsed())
        report = self._build_report(state)
        progress("report", "done", f"{len(report.methodologies)} 方法 {len(report.claims)} 观点 {len(report.limitations)} 局限", _elapsed())

        return report

    # ── 各阶段 ────────────────────────────

    def _phase_parse(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        try:
            state.paper = self.parser.parse(state.paper_path, on_progress=progress)
            n_sec = len(state.paper.sections)
            n_para = sum(len(s.paragraphs) for s in state.paper.sections)
            n_char = len(state.paper.raw_text)
            progress("parse", "done", f"{n_sec} 章节, {n_para} 段落, ~{n_char} 字符", elapsed())
        except Exception as e:
            state.errors.append(f"解析失败: {e}")
            progress("parse", "error", str(e), elapsed())

    def _phase_extract(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        if state.paper is None:
            return
        try:
            progress("extract", "step", "发送请求到 LLM，等待响应...", elapsed())
            methods, claims, exps = self.extractor.extract(state.paper, on_progress=progress)
            state.methodologies = methods
            state.claims = claims
            state.experiments = exps
            progress(
                "extract", "done",
                f"{len(methods)} 个方法论, {len(claims)} 条观点",
                elapsed(),
            )
            # 打印提取到的方法名和观点摘要
            for m in methods:
                progress("extract", "sub", f"方法: {m.name} [{m.category}]", elapsed())
            for c in claims[:3]:
                progress("extract", "sub", f"观点: {c.statement[:80]}", elapsed())
            if len(claims) > 3:
                progress("extract", "sub", f"... 及其他 {len(claims) - 3} 条观点", elapsed())
        except Exception as e:
            state.errors.append(f"提取失败: {e}")
            progress("extract", "error", str(e), elapsed())

    def _phase_validate(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        if not state.claims:
            progress("validate", "skip", "无观点可验证", elapsed())
            return

        from ..sandbox.sandbox import CodeSandbox

        if self.validator.sandbox is None:
            progress("validate", "step", "初始化代码沙箱...", elapsed())
            self.validator.sandbox = CodeSandbox()

        total = len(state.claims)
        for i, claim in enumerate(state.claims):
            n = i + 1
            progress("validate", "step", f"[{n}/{total}] {claim.id}: {claim.statement[:60]}", elapsed())
            try:
                result = self.validator.validate(claim, on_progress=progress)
                state.validations.append(result)
                icon = {"supported": "+", "partially_supported": "~", "not_supported": "-", "unverifiable": "?", "error": "x"}
                progress("validate", "sub", f"{claim.id} → {icon.get(result.verdict.value, '?')} {result.verdict.value}", elapsed())
            except Exception as e:
                state.errors.append(f"验证 {claim.id} 失败: {e}")
                progress("validate", "sub", f"{claim.id}: 失败 ({e})", elapsed())

        n_supported = sum(1 for v in state.validations if v.verdict.value == "supported")
        progress("validate", "done", f"{len(state.validations)}/{total} 条完成 ({n_supported} 支持)", elapsed())

    def _phase_analyze(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        if state.paper is None:
            return
        try:
            progress("analyze", "step", "从方法/实验/理论/可复现/泛化/伦理 6 维度审查...", elapsed())
            state.limitations = self.analyzer.analyze(
                state.paper, state.claims, state.experiments
            )
            # 统计严重性分布
            crit = sum(1 for l in state.limitations if l.severity == "critical")
            high = sum(1 for l in state.limitations if l.severity == "high")
            progress(
                "analyze", "done",
                f"{len(state.limitations)} 条局限性 (critical: {crit}, high: {high})",
                elapsed(),
            )
            for lim in state.limitations[:3]:
                progress("analyze", "sub", f"[{lim.severity}] {lim.description[:80]}", elapsed())
            if len(state.limitations) > 3:
                progress("analyze", "sub", f"... 及其他 {len(state.limitations) - 3} 条", elapsed())
        except Exception as e:
            state.errors.append(f"局限性分析失败: {e}")
            progress("analyze", "error", str(e), elapsed())

    def _phase_summarize(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        if not state.claims:
            progress("summarize", "skip", "无观点可总结", elapsed())
            return
        try:
            n_claims = len(state.claims)
            progress("summarize", "step", f"总结 {n_claims} 条主张 + 整篇论文...", elapsed())
            paper_year = state.paper.meta.year if state.paper else None
            summary_map, overall = self.summarizer.summarize(
                claims=state.claims,
                methodologies=state.methodologies,
                limitations=state.limitations,
                paper_year=paper_year,
            )
            # 将 per-claim 摘要写入 Claim 对象
            for claim in state.claims:
                if claim.id in summary_map:
                    claim.summary = summary_map[claim.id]

            state._summary_overall = overall
            progress(
                "summarize", "done",
                f"{len(summary_map)} 条 claim 摘要 + 整体总结",
                elapsed(),
            )
            for claim in state.claims[:3]:
                if claim.summary:
                    progress("summarize", "sub", f"{claim.id}: {claim.summary[:80]}", elapsed())
        except Exception as e:
            state.errors.append(f"总结失败: {e}")
            progress("summarize", "error", str(e), elapsed())

    def _build_report(self, state: PipelineState) -> AnalysisReport:
        if state.paper is None:
            raise RuntimeError("无法生成报告: 论文解析失败")

        overall = getattr(state, "_summary_overall", "")
        if not overall:
            parts = [f"提取 {len(state.methodologies)} 个方法"]
            parts.append(f"{len(state.claims)} 条观点")
            if state.validations:
                parts.append(f"验证 {len(state.validations)} 条")
            parts.append(f"发现 {len(state.limitations)} 条局限性")
            if state.errors:
                parts.append(f"错误: {'; '.join(state.errors)}")
            overall = "，".join(parts) + "。"

        return AnalysisReport(
            paper=state.paper.meta,
            methodologies=state.methodologies,
            claims=state.claims,
            experiments=state.experiments,
            validations=state.validations,
            limitations=state.limitations,
            overall_score=0,
            summary=overall,
        )


def _strip_dollar_signs(s: str) -> str:
    """去除字符串两端的 $ 或 $$ 符号."""
    s = s.strip()
    while s.startswith("$$") and s.endswith("$$"):
        s = s[2:-2].strip()
    while s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    return s


# ── 报告导出 ──────────────────────────────

def report_to_markdown(report: AnalysisReport) -> str:
    """将报告渲染为 Markdown.

    章节顺序: 摘要 → 方法论 → 核心观点 → 验证结果 → 局限性 → 总结
    观点排版: 假设在前，主张在后.
    """
    lines: list[str] = []

    p = report.paper
    lines.append(f"# 论文分析报告: {p.title}")
    lines.append(f"\n- **分析时间**: {report.analyzed_at}")
    if p.arxiv_id:
        lines.append(f"- **arXiv**: [{p.arxiv_id}](https://arxiv.org/abs/{p.arxiv_id})")
    if p.year:
        lines.append(f"- **发表年份**: {p.year}")
    if p.doi:
        lines.append(f"- **DOI**: [{p.doi}](https://doi.org/{p.doi})")

    # 摘要
    if p.abstract:
        lines.append(f"\n## 摘要\n{p.abstract}")

    # ── 方法论 ──
    if report.methodologies:
        lines.append("\n## 方法论")
        for m in report.methodologies:
            cat_tag = f" [{m.category}]" if m.category else ""
            lines.append(f"\n### {m.id} {m.name}{cat_tag}")
            if m.overview:
                lines.append(f"\n{m.overview}")
            if m.innovations:
                lines.append("\n**创新点**:")
                for inn in m.innovations:
                    lines.append(f"- {inn}")
            if m.inputs:
                lines.append(f"\n**输入**: {m.inputs}")
            if m.outputs:
                lines.append(f"**输出**: {m.outputs}")
            if m.procedure:
                lines.append("\n**步骤**:")
                for step in m.procedure:
                    lines.append(f"{step}")
            if m.key_formulas:
                lines.append("\n**关键公式**:")
                for fm in m.key_formulas:
                    clean = _strip_dollar_signs(fm)
                    if clean:
                        lines.append(f"\n$$\n{clean}\n$$")

    # ── 核心观点 ──
    if report.claims:
        lines.append("\n## 核心观点")
        for c in report.claims:
            method_refs = f" [→ {', '.join(c.related_method_ids)}]" if c.related_method_ids else ""
            type_zh = CLAIM_TYPE_ZH.get(c.type.value, c.type.value)
            lines.append(f"\n### {c.id} [{type_zh}]{method_refs}")

            # 一句话摘要（最显眼位置）
            if c.summary:
                lines.append(f"> **{c.summary}**")

            fields = [
                ("问题", c.problem),
                ("方法", c.method_applied),
                ("机制", c.mechanism),
                ("结果", c.result),
                ("前提", c.condition),
            ]
            for label, value in fields:
                if value:
                    lines.append(f"- **{label}**: {value}")

            if c.assumptions:
                lines.append(f"- **隐含假设**: {'; '.join(c.assumptions)}")
            if c.context:
                lines.append(f"> 原文: {c.context[:200]}")
            lines.append(f"  *置信度: {c.confidence:.0%}*")

    # ── 验证结果 ──
    if report.validations:
        lines.append("\n## 验证结果")
        for v in report.validations:
            emoji = {"supported": "✅", "partially_supported": "⚠️", "not_supported": "❌", "unverifiable": "❓", "error": "💥"}
            icon = emoji.get(v.verdict.value, "❓")
            verdict_zh = VERDICT_ZH.get(v.verdict.value, v.verdict.value)
            lines.append(f"\n### {icon} {v.claim_id} — {verdict_zh}")
            if v.evidence:
                lines.append(v.evidence[:500])
            if v.generated_code:
                lines.append(f"\n<details><summary>验证代码</summary>\n\n```python\n{v.generated_code}\n```\n</details>")
            if v.execution_output:
                lines.append(f"\n<details><summary>执行输出</summary>\n\n```\n{v.execution_output}\n```\n</details>")

    # ── 局限性 ──
    if report.limitations:
        lines.append("\n## 局限性分析")
        for lim in report.limitations:
            cat_zh = LIMITATION_CATEGORY_ZH.get(lim.category.value, lim.category.value)
            sev_zh = SEVERITY_ZH.get(lim.severity, lim.severity)
            lines.append(f"\n- **[{cat_zh}]** ({sev_zh}) {lim.description}")
            if lim.suggested_fix:
                lines.append(f"  > 建议: {lim.suggested_fix}")

    # ── 总结 ──
    lines.append(f"\n## 总结\n{report.summary}")

    return "\n".join(lines)


def _sanitize_filename(s: str, max_len: int = 80) -> str:
    """替换 Windows/macOS/Linux 文件名中的非法字符."""
    # 非法字符集合: Windows < > : " / \ | ? *  + 控制字符
    invalid = '<>:"/\\|?*\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f'
    result = s.translate(str.maketrans({c: "_" for c in invalid}))
    result = result.strip(". ")  # Windows 不允许末尾为 . 或空格
    if not result:
        result = "paper"
    return result[:max_len]


def save_report(report: AnalysisReport, output_dir: str | Path = "output") -> Path:
    """保存报告为 Markdown 和 JSON 文件."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    title_slug = _sanitize_filename(report.paper.title[:50])
    stem = f"{title_slug}_{report.analyzed_at[:10]}"

    # JSON（完整数据）
    json_path = output_dir / f"{stem}.json"
    json_path.write_text(report.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown（可读报告）
    md_path = output_dir / f"{stem}.md"
    md_path.write_text(report_to_markdown(report), encoding="utf-8")

    return json_path
