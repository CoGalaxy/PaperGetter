"""局限性分析器.

从方法论、实验、理论、可复现性、泛化性等多个维度审视论文.
"""

from __future__ import annotations

from ..models.paper import Paper, Claim, Limitation, LimitationCategory, CLAIM_TYPE_ZH
from ..llm.client import LLMClient


LIMITATION_PROMPT = """你是一位严格的论文审稿人。请系统性地分析这篇论文的局限性。

论文标题: {title}
摘要: {abstract}

核心主张:
{claims}

实验描述:
{experiments}

请从以下维度逐一分析:

1. **方法局限** (method): 算法/架构本身有什么不足？计算复杂度？可扩展性？对超参的敏感度？
2. **实验局限** (experiment): 数据集是否充分？基线是否公平？消融实验是否完整？有无显著性检验？
3. **理论局限** (theory): 证明的假设是否过强？定理的结论是否和实验一致？
4. **可复现性** (reproducibility): 是否开源代码？超参是否完整公开？计算资源需求多大？
5. **泛化性** (generalization): 在真实场景中适用吗？跨领域/跨语言/跨分布效果如何？
6. **伦理** (ethics): 是否存在偏见风险？隐私问题？可能被误用？

对每条局限性，给出:
- category: 类别
- description: 具体描述（中文）
- severity: low/medium/high/critical
- suggested_fix: 如果可以改进，给出建议

要求:
- **最多列出 6 条**，按严重性从高到低排列，确保覆盖不同维度
- 每条局限性必须具体，应当结合论文内容，不要泛泛而谈
- 如果某维度没有问题，可以不说
- 重点关注这篇论文特有的问题，而非该领域通用的局限
- 如果潜在问题很多，优先选最致命的（critical/high severity）
"""


class LimitationAnalyzer:
    """多维度局限性分析."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def analyze(
        self,
        paper: Paper,
        claims: list[Claim],
        experiments: list,
    ) -> list[Limitation]:
        """分析论文的局限性."""
        # 构建分析输入
        prompt = LIMITATION_PROMPT.format(
            title=paper.meta.title,
            abstract=paper.meta.abstract,
            claims=self._format_claims(claims),
            experiments=self._format_experiments(experiments),
        )

        result = self.llm.structured(
            messages=[
                {
                    "role": "system",
                    "content": "You are a critical paper reviewer. Output valid JSON matching the schema.",
                },
                {"role": "user", "content": prompt},
            ],
            response_model=LimitationResult,
            task="limitation",
            temperature=0.2,
        )

        return result.to_models()

    @staticmethod
    def _format_claims(claims: list[Claim]) -> str:
        if not claims:
            return "（暂未提取）"
        lines: list[str] = []
        for c in claims:
            type_zh = CLAIM_TYPE_ZH.get(c.type.value, c.type.value)
            lines.append(f"- [{type_zh}] 问题: {c.problem}")
            lines.append(f"  方法: {c.method_applied}")
            lines.append(f"  机制: {c.mechanism}")
            lines.append(f"  结果: {c.result}")
            lines.append(f"  前提: {c.condition}")
            if c.assumptions:
                lines.append(f"  假设: {'; '.join(c.assumptions)}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_experiments(experiments: list) -> str:
        if not experiments:
            return "（暂未提取）"
        lines = [f"- 数据集: {e.dataset}, 基线: {', '.join(e.baselines)}, 指标: {', '.join(e.metrics)}" for e in experiments]
        return "\n".join(lines)


# ── 结构化输出辅助 ──────────────────────────

from pydantic import BaseModel, Field


class LimitationItem(BaseModel):
    category: str = Field(description="method | experiment | theory | reproducibility | generalization | ethics")
    description: str
    severity: str = Field(default="medium")
    related_claim_indices: list[int] = Field(default_factory=list)
    suggested_fix: str = ""


class LimitationResult(BaseModel):
    limitations: list[LimitationItem] = Field(default_factory=list)

    def to_models(self) -> list[Limitation]:
        out: list[Limitation] = []
        for item in self.limitations:
            out.append(
                Limitation(
                    category=item.category,  # type: ignore[arg-type]
                    description=item.description,
                    severity=item.severity,
                    related_claim_ids=[f"claim-{idx + 1:03d}" for idx in item.related_claim_indices],
                    suggested_fix=item.suggested_fix,
                )
            )
        return out
