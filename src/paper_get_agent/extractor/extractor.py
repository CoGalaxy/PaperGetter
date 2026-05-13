"""观点提取器.

从结构化论文中识别和抽取:
- 方法论 (methodologies): 论文提出的具体方法、算法、框架
- 核心观点 (claims): 对方法效果的主张
"""

from __future__ import annotations

from ..models.paper import Paper, Claim, Experiment, Methodology
from ..llm.client import LLMClient


EXTRACTION_PROMPT = """你是一位资深论文审稿人。请仔细阅读以下论文，完成两项任务:

---

## 任务 1: 提取方法论（methodologies）

论文提出了哪些**具体的方法/算法/框架/流程**？对每个方法，请提取:

1. name: 方法名称（如 "DeepFM Network" / "Modified Focal Loss"）
2. category: 归类 — "模型架构" / "损失函数" / "数据预处理" / "训练策略" / "评估框架" / "特征工程"
3. overview: 一段话概述（3-5句），说清楚这个方法做什么、怎么做
4. procedure: 具体步骤列表，每步一句话（如 ["1. 对离散特征做 one-hot 编码", "2. 连续特征做 min-max 归一化", ...]）
5. key_formulas: 关键数学公式的 LaTeX 字符串列表（只提取论文中明确给出的核心公式，不要编造）
6. innovations: 与已有方法的区别/创新点列表
7. inputs: 方法接受什么输入
8. outputs: 方法产出什么输出

要求:
- 方法论回答"怎么做"的问题，重要的是步骤和公式
- 论文中每个独立提出的方法都应被提取
- 如果论文的方法是一个完整 pipeline，既列出整体流程，也提取关键组件
- 关键数学公式需要在 markdown 中能正确显示（行内公式用 $...$，块级公式用 $$...$$）
- 需要注明公式中变量的含义
- 方法论必须要按照论文中的逻辑顺序给出，尽量做到前后连贯

---

## 任务 2: 提取核心观点（claims）

对论文中的每项核心主张:

1. type: "theoretical"(理论/数学证明), "empirical"(实验验证), "comparative"(对比分析), "design"(架构/算法设计)
2. statement: 一句话概括（中英文均可，建议中文）
3. assumptions: **该主张成立所需要的隐含假设/前提条件**（这很重要，请仔细推导）
4. context: 原文中支撑该 claim 的关键句子（直接引用）
5. confidence: 你对该主张可靠性的初步判断 (0.0-1.0)，考虑:
   - 是否有消融实验支持
   - 是否与常识矛盾
   - 论证逻辑是否严密

要求:
- 只提取有实质内容的主张，忽略背景介绍和文献综述
- 每条 claim 应该可独立验证
- assumptions 要仔细推导：这个主张在什么前提下才成立？缺了什么就不对？
- 关键数学公式需要在 markdown 中能正确显示（行内公式用 $...$，块级公式用 $$...$$）
- 需要注明公式中变量的含义


---

论文内容:
---
{paper_content}
---

请同时输出 methodologies 和 claims。"""


class ClaimExtractor:
    """从 Paper 中提取方法论和核心主张."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def extract(
        self, paper: Paper, on_progress=None
    ) -> tuple[list[Methodology], list[Claim], list[Experiment]]:
        """提取论文的方法论、核心主张和实验描述."""
        progress = on_progress or (lambda p, s, d, e: None)

        content = self._build_content(paper)
        progress("extract", "step", f"构建 prompt 完成，共 {len(content)} 字符", 0)

        progress("extract", "step", "等待 LLM 响应（可能需要 30-60 秒）...", 0)
        result = self.llm.structured(
            messages=[
                {
                    "role": "system",
                    "content": "You are a meticulous paper reviewer. Always output valid JSON matching the requested schema.",
                },
                {"role": "user", "content": EXTRACTION_PROMPT.format(paper_content=content)},
            ],
            response_model=ExtractionResult,
            task="extraction",
            temperature=0.1,
        )
        progress("extract", "step", "LLM 响应完成，正在解析...", 0)

        methods, claims, exps = result.to_models()
        return methods, claims, exps

    def _build_content(self, paper: Paper) -> str:
        """构建送给 LLM 的论文文本."""
        parts: list[str] = []

        parts.append(f"# 标题\n{paper.meta.title}")
        if paper.meta.abstract:
            parts.append(f"\n# 摘要\n{paper.meta.abstract}")

        for sec in paper.sections:
            text = "\n".join(sec.paragraphs)
            parts.append(f"\n# {sec.heading}\n{text}")

        full = "\n".join(parts)
        if len(full) > 64000:
            full = full[:64000] + "\n\n[内容过长，已截断...]"

        return full


# ── LLM 结构化输出辅助模型 ────────────────────

from pydantic import BaseModel, Field


class MethodologyItem(BaseModel):
    name: str
    category: str = ""
    overview: str = ""
    procedure: list[str] = Field(default_factory=list)
    key_formulas: list[str] = Field(default_factory=list)
    innovations: list[str] = Field(default_factory=list)
    inputs: str = ""
    outputs: str = ""


class ClaimItem(BaseModel):
    type: str = Field(description="theoretical | empirical | comparative | design")
    statement: str
    assumptions: list[str] = Field(default_factory=list)
    context: str = ""
    confidence: float = Field(default=0.5)


class ExtractionResult(BaseModel):
    methodologies: list[MethodologyItem] = Field(default_factory=list)
    claims: list[ClaimItem] = Field(default_factory=list)

    def to_models(self) -> tuple[list[Methodology], list[Claim], list[Experiment]]:
        methods_out: list[Methodology] = []
        for i, m in enumerate(self.methodologies):
            methods_out.append(
                Methodology(
                    id=f"method-{i + 1:03d}",
                    name=m.name,
                    category=m.category,
                    overview=m.overview,
                    procedure=m.procedure,
                    key_formulas=m.key_formulas,
                    innovations=m.innovations,
                    inputs=m.inputs,
                    outputs=m.outputs,
                )
            )

        claims_out: list[Claim] = []
        for i, item in enumerate(self.claims):
            claim_id = f"claim-{i + 1:03d}"
            claims_out.append(
                Claim(
                    id=claim_id,
                    type=item.type,  # type: ignore[arg-type]
                    statement=item.statement,
                    context=item.context,
                    assumptions=item.assumptions,
                    confidence=item.confidence,
                )
            )

        # experiments 暂时预留，后续单独提取
        return methods_out, claims_out, []
