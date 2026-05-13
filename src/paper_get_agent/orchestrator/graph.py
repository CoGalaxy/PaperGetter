"""编排器.

将解析、提取、验证、分析四个阶段串联为完整流水线.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..models.paper import Paper, Claim, Experiment, Methodology, ValidationResult, Limitation, AnalysisReport
from ..parser.parser import PaperParser
from ..extractor.extractor import ClaimExtractor
from ..validator.validator import ClaimValidator
from ..analyzer.analyzer import LimitationAnalyzer
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

        # Phase 1: 解析
        progress("parse", "start", "打开 PDF 并提取文本...", _elapsed())
        self._phase_parse(state, progress, _elapsed)

        # Phase 2: 提取观点
        progress("extract", "start", "调用 LLM 提取核心观点...", _elapsed())
        self._phase_extract(state, progress, _elapsed)

        # Phase 3: 验证（可选）
        if not self.skip_validation:
            progress("validate", "start", "", _elapsed())
            self._phase_validate(state, progress, _elapsed)

        # Phase 4: 局限性分析
        progress("analyze", "start", "调用 LLM 分析局限性...", _elapsed())
        self._phase_analyze(state, progress, _elapsed)

        # 生成报告
        progress("report", "start", "生成分析报告...", _elapsed())
        report = self._build_report(state)
        progress("report", "done", f"报告生成完毕，评分 {report.overall_score}/10", _elapsed())

        return report

    # ── 各阶段 ────────────────────────────

    def _phase_parse(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        try:
            state.paper = self.parser.parse(state.paper_path, on_progress=progress)
            n_sec = len(state.paper.sections)
            n_para = sum(len(s.paragraphs) for s in state.paper.sections)
            progress("parse", "done", f"解析完成: {n_sec} 个章节, {n_para} 个段落", elapsed())
        except Exception as e:
            state.errors.append(f"解析失败: {e}")
            progress("parse", "error", str(e), elapsed())

    def _phase_extract(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        if state.paper is None:
            return
        try:
            methods, claims, exps = self.extractor.extract(state.paper, on_progress=progress)
            state.methodologies = methods
            state.claims = claims
            state.experiments = exps
            progress(
                "extract", "done",
                f"提取完成: {len(methods)} 个方法, {len(claims)} 条观点",
                elapsed(),
            )
        except Exception as e:
            state.errors.append(f"提取失败: {e}")
            progress("extract", "error", str(e), elapsed())

    def _phase_validate(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        if not state.claims:
            progress("validate", "skip", "无观点可验证", elapsed())
            return

        from ..sandbox.sandbox import CodeSandbox

        if self.validator.sandbox is None:
            self.validator.sandbox = CodeSandbox()

        total = len(state.claims)
        for i, claim in enumerate(state.claims):
            n = i + 1
            progress("validate", "step", f"[{n}/{total}] 验证 {claim.id}: {claim.statement[:60]}...", elapsed())
            try:
                result = self.validator.validate(claim, on_progress=progress)
                state.validations.append(result)
                icon = {"supported": "+", "partially_supported": "~", "not_supported": "-", "unverifiable": "?", "error": "x"}
                progress("validate", "sub", f"{claim.id} → {icon.get(result.verdict.value, '?')} {result.verdict.value}", elapsed())
            except Exception as e:
                state.errors.append(f"验证 {claim.id} 失败: {e}")
                progress("validate", "error", f"{claim.id}: {e}", elapsed())

        progress("validate", "done", f"验证完毕: {len(state.validations)}/{total} 条", elapsed())

    def _phase_analyze(self, state: PipelineState, progress: Callable, elapsed: Callable) -> None:
        if state.paper is None:
            return
        try:
            state.limitations = self.analyzer.analyze(
                state.paper, state.claims, state.experiments
            )
            progress("analyze", "done", f"分析完成: {len(state.limitations)} 条局限性", elapsed())
        except Exception as e:
            state.errors.append(f"局限性分析失败: {e}")
            progress("analyze", "error", str(e), elapsed())

    def _build_report(self, state: PipelineState) -> AnalysisReport:
        if state.paper is None:
            raise RuntimeError("无法生成报告: 论文解析失败")

        # 综合评分: 基准 6.0 + 方法论加分 + 验证加分 - 局限性扣分
        score = 6.0
        if state.methodologies:
            score += min(1.5, len(state.methodologies) * 0.5)
        if state.validations:
            supported = sum(1 for v in state.validations if v.verdict.value == "supported")
            not_supported = sum(1 for v in state.validations if v.verdict.value == "not_supported")
            score += (supported - not_supported) * 0.5
        for lim in state.limitations:
            if lim.severity == "critical":
                score -= 0.5
            elif lim.severity == "high":
                score -= 0.3
        score = max(1.0, min(10.0, score))

        parts = [f"提取 {len(state.methodologies)} 个方法"]
        parts.append(f"{len(state.claims)} 条观点")
        if state.validations:
            parts.append(f"验证 {len(state.validations)} 条")
        parts.append(f"发现 {len(state.limitations)} 条局限性")
        if state.errors:
            parts.append(f"错误: {'; '.join(state.errors)}")

        return AnalysisReport(
            paper=state.paper.meta,
            methodologies=state.methodologies,
            claims=state.claims,
            experiments=state.experiments,
            validations=state.validations,
            limitations=state.limitations,
            overall_score=round(score, 1),
            summary="，".join(parts) + "。",
        )


# ── 报告导出 ──────────────────────────────

def report_to_markdown(report: AnalysisReport) -> str:
    """将报告渲染为 Markdown.

    章节顺序: 摘要 → 方法论 → 核心观点 → 验证结果 → 局限性 → 总结
    观点排版: 假设在前，主张在后.
    """
    lines: list[str] = []

    p = report.paper
    lines.append(f"# 论文分析报告: {p.title}")
    lines.append(f"\n- **评分**: {report.overall_score}/10")
    lines.append(f"- **分析时间**: {report.analyzed_at}")
    if p.arxiv_id:
        lines.append(f"- **arXiv**: [{p.arxiv_id}](https://arxiv.org/abs/{p.arxiv_id})")
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
                    lines.append(f"$${fm}$$")

    # ── 核心观点 ──
    if report.claims:
        lines.append("\n## 核心观点")
        for c in report.claims:
            lines.append(f"\n### {c.id} [{c.type.value}]")
            # 假设在前
            if c.assumptions:
                lines.append(f"**前提假设**: {'; '.join(c.assumptions)}")
            # 主张在后
            lines.append(f"**主张**: {c.statement}")
            if c.context:
                lines.append(f"> 原文: {c.context[:200]}")

    # ── 验证结果 ──
    if report.validations:
        lines.append("\n## 验证结果")
        for v in report.validations:
            emoji = {"supported": "✅", "partially_supported": "⚠️", "not_supported": "❌", "unverifiable": "❓", "error": "💥"}
            icon = emoji.get(v.verdict.value, "❓")
            lines.append(f"\n### {icon} {v.claim_id} — {v.verdict.value}")
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
            lines.append(f"\n- **[{lim.category.value}]** ({lim.severity}) {lim.description}")
            if lim.suggested_fix:
                lines.append(f"  > 建议: {lim.suggested_fix}")

    # ── 总结 ──
    lines.append(f"\n## 总结\n{report.summary}")

    return "\n".join(lines)


def save_report(report: AnalysisReport, output_dir: str | Path = "output") -> Path:
    """保存报告为 Markdown 和 JSON 文件."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    title_slug = report.paper.title[:50].replace(" ", "_").replace("/", "_")
    stem = f"{title_slug}_{report.analyzed_at[:10]}"

    # JSON（完整数据）
    json_path = output_dir / f"{stem}.json"
    json_path.write_text(report.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown（可读报告）
    md_path = output_dir / f"{stem}.md"
    md_path.write_text(report_to_markdown(report), encoding="utf-8")

    return json_path
