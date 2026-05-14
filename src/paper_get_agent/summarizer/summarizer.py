"""论文总结器.

独立 Agent，负责两项总结任务:
  1. 为每条 claim 生成一句话摘要（嵌入到 claim 中）
  2. 为整篇论文生成综合总结（写入报告）
"""

from __future__ import annotations

from ..models.paper import Claim, Limitation, Methodology
from ..llm.client import LLMClient


SUMMARIZE_PROMPT = """你是一位资深论文审稿人，请根据以下析出的内容，完成两项总结任务。

---

## 任务 1: 为每条主张写一句话总结

每条主张给出了完整的因果链（问题→方法→机制→结果→前提）。请为每条主张写一句**极其简洁**的总结（≤40 字），抓住核心逻辑。

格式要求:
- 一句话说清: "通过[方法]，解决[问题]，实现[关键结果]"
- 不要重复 causality chain 的所有细节，提炼最核心的一点
- 中文

---

## 任务 2: 撰写整篇论文的综合总结

综合以下所有信息，写一份 2-3 段的论文总结:

- 论文的方法论列表
- 核心主张及其验证状态
- 发现的局限性

总结应包含:
1. **论文贡献概述** (1 段): 这篇论文做了什么、用了什么方法、核心创新在哪
2. **关键发现与证据** (1 段): 主要实验结果/理论结果是什么、论证力度如何
3. **整体评价** (1 段): 论文的优势与不足、可复现性、泛化性方面的总体判断

文风: 客观、精炼、适合放在审稿报告的"总结"章节。

---

{year_note}

---

## 输入数据

方法论（共 {n_methods} 个）:
{methods}

核心主张（共 {n_claims} 条）:
{claims}

局限性（共 {n_limitations} 条）:
{limitations}
"""


class PaperSummarizer:
    """论文总结 Agent — 独立于提取/验证/分析."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def summarize(
        self,
        claims: list[Claim],
        methodologies: list[Methodology],
        limitations: list[Limitation],
        paper_year: int | None = None,
    ) -> tuple[dict[str, str], str]:
        """生成每条 claim 的摘要 + 整篇论文的总结.

        Returns:
            (claim_id → summary, overall_summary)
        """
        if paper_year:
            year_note = f"注意: 这篇论文发表于 {paper_year} 年。请结合其发表年代的历史语境进行评价——不应以当下的标准苛求当时的工作，但可以客观指出其时代局限性。"
        else:
            year_note = ""
        prompt = SUMMARIZE_PROMPT.format(
            year_note=year_note,
            n_methods=len(methodologies),
            methods=self._format_methods(methodologies),
            n_claims=len(claims),
            claims=self._format_claims(claims),
            n_limitations=len(limitations),
            limitations=self._format_limitations(limitations),
        )

        result = self.llm.structured(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior paper reviewer writing the final summary section. "
                        "Output valid JSON matching the requested schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_model=SummarizationResult,
            task="summarization",
            temperature=0.1,
        )

        claim_summaries: dict[str, str] = {}
        for item in result.claim_summaries:
            claim_summaries[item.claim_id] = item.summary

        return claim_summaries, result.overall_summary

    @staticmethod
    def _format_methods(methods: list[Methodology]) -> str:
        if not methods:
            return "（无）"
        lines: list[str] = []
        for m in methods:
            lines.append(f"- {m.id}: {m.name} [{m.category}]")
            if m.overview:
                lines.append(f"  {m.overview[:150]}")
        return "\n".join(lines)

    @staticmethod
    def _format_claims(claims: list[Claim]) -> str:
        if not claims:
            return "（无）"
        lines: list[str] = []
        for c in claims:
            lines.append(f"\n### {c.id} [{c.type.value}]")
            lines.append(f"- 问题: {c.problem}")
            lines.append(f"- 方法: {c.method_applied}")
            lines.append(f"- 机制: {c.mechanism}")
            lines.append(f"- 结果: {c.result}")
            lines.append(f"- 前提: {c.condition}")
            if c.assumptions:
                lines.append(f"- 假设: {'; '.join(c.assumptions)}")
        return "\n".join(lines)

    @staticmethod
    def _format_limitations(limitations: list[Limitation]) -> str:
        if not limitations:
            return "（无）"
        lines: list[str] = []
        for lim in limitations:
            lines.append(f"- [{lim.severity}] [{lim.category.value}] {lim.description[:200]}")
        return "\n".join(lines)


# ── 结构化输出模型 ──────────────────────────

from pydantic import BaseModel, Field


class ClaimSummaryItem(BaseModel):
    claim_id: str = Field(description="claim ID, e.g. claim-001")
    summary: str = Field(description="一句话总结 (≤40 字)")


class SummarizationResult(BaseModel):
    claim_summaries: list[ClaimSummaryItem] = Field(default_factory=list)
    overall_summary: str = Field(description="2-3 段论文综合总结")
