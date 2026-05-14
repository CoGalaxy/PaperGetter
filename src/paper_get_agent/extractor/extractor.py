"""观点提取器.

两阶段提取:
  Pass 1: 提取方法论骨架（名称、步骤、公式、创新点）
  Pass 2: 对每个方法提取因果链主张 + 前提展开 + 去重合并
"""

from __future__ import annotations

from ..models.paper import Paper, Claim, Experiment, Methodology
from ..llm.client import LLMClient


# ── Pass 1: 方法论骨架提取 ──────────────────

METHOD_PROMPT = """你是一位资深论文审稿人。请仔细阅读以下论文，提取论文提出的核心方法论。

对每个方法，提供:

1. name: 方法名称
2. category: "模型架构" / "损失函数" / "数据预处理" / "训练策略" / "评估框架" / "系统设计" / "通信协议"
3. overview: 一段话概述（3-5句），说清楚做什么、怎么做
4. procedure: 具体步骤列表，每步一句话
5. key_formulas: 关键数学公式的 LaTeX 表达式。只输出 LaTeX 代码本身，**不要**加 $ 或 $$ 符号
6. innovations: 与已有方法的区别/创新点列表
7. inputs: 方法接受什么输入
8. outputs: 方法产出什么输出

要求:
- 最多提取 **5 个** 方法
- 只提取论文的原创贡献，不提取背景介绍中的已有方法
- 如果论文是一个完整 pipeline，同时提取整体流程和关键组件
- 步骤要具体，关键的公式要附上
- 按论文中的逻辑顺序排列

论文内容:
---
{paper_content}
---
"""


# ── Pass 2: 因果链主张提取 + 去重 ──────────

CLAIM_PROMPT = """你是一位严格的论文审稿人。以下论文提出了若干方法（见下方"已提取的方法"），请对每个方法提取其支撑的核心主张。

## 主张格式：因果链

每条主张必须填满以下**五个环节**（每个环节 1-3 句话）：

1. **problem** —— 针对/解决了什么具体问题？
2. **method_applied** —— 应用了什么方法或技术手段？
3. **mechanism** —— 该方法**为什么**能解决问题？因果逻辑是什么？【最核心字段，必须具体说明因果链条】
4. **result** —— 产生了什么效果？有量化结果的附上量化数据。
5. **condition** —— 在什么假设/前提下成立？什么情况会导致不成立？

如果原文对某个环节没有明确论述，请在字段中写"**缺失：原文未论述**"——不要编造。

## 类型

type 取: "theoretical"(理论证明) / "empirical"(实验验证) / "comparative"(对比分析) / "design"(架构设计)

## 去重与合并

- 每条方法最多提取 2 条主张
- 检查所有主张：是否存在本质相同的论证（>50% 重叠）？如有，合并为一条更完整的主张
- 合并后最多保留 **4-5 条**，确保覆盖论文的不同贡献维度
- 如果论文中不同实验都在论证同一个核心观点，合并为一条

## 前提假设展开

对每条最终保留的主张：
- 推导其成立所需的**隐含假设/前提条件**
- 自问：缺了什么前提，这个主张就不成立？
- 将推导出的假设填入 assumptions 字段
- 根据因果链的完整性、假设的合理性、实验支撑力度，赋值 confidence (0.0-1.0)

## 关联

related_method_indices 标记该主张涉及的方法索引（从 0 开始，对应下方方法列表的顺序）。

---

已提取的方法（共 {method_count} 个）：
{methods_text}

---

论文内容:
---
{paper_content}
---
"""


# ── 提取器 ──────────────────────────────────

class ClaimExtractor:
    """两阶段提取: 先方法骨架，再因果链主张."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def extract(
        self, paper: Paper, on_progress=None
    ) -> tuple[list[Methodology], list[Claim], list[Experiment]]:
        progress = on_progress or (lambda p, s, d, e: None)
        content = self._build_content(paper)

        # ── Pass 1: 提取方法骨架 ──
        progress("extract", "step", "Pass 1/2: 提取方法论骨架...", 0)
        methods = self._extract_methods(content, progress)

        if not methods:
            progress("extract", "step", "未提取到方法，跳过主张提取", 0)
            return [], [], []

        progress("extract", "step", f"Pass 1 完成: {len(methods)} 个方法", 0)

        # ── Pass 2: 因果链主张提取 + 去重 ──
        progress("extract", "step", f"Pass 2/2: 对 {len(methods)} 个方法提取因果链主张...", 0)
        claims = self._extract_claims(content, methods, progress)
        progress("extract", "step", f"Pass 2 完成: {len(claims)} 条主张（已去重）", 0)

        return methods, claims, []

    def _extract_methods(
        self, content: str, progress
    ) -> list[Methodology]:
        """Pass 1: 提取方法论骨架."""
        progress("extract", "step", "等待 LLM 提取方法...", 0)
        result = self.llm.structured(
            messages=[
                {
                    "role": "system",
                    "content": "You are a meticulous paper reviewer. Output valid JSON matching the requested schema.",
                },
                {"role": "user", "content": METHOD_PROMPT.format(paper_content=content)},
            ],
            response_model=MethodResult,
            task="extraction",
            temperature=0.1,
        )
        return result.to_methods()

    def _extract_claims(
        self, content: str, methods: list[Methodology], progress
    ) -> list[Claim]:
        """Pass 2: 因果链主张提取 + 去重合并."""
        methods_text = self._format_methods_for_claim_prompt(methods)
        prompt = CLAIM_PROMPT.format(
            method_count=len(methods),
            methods_text=methods_text,
            paper_content=content,
        )
        progress("extract", "step", "等待 LLM 提取主张（含去重）...", 0)
        result = self.llm.structured(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a critical paper reviewer. "
                        "For each claim, you MUST fill ALL five causal chain fields. "
                        "If the paper does not provide information for a field, write '缺失：原文未论述'. "
                        "Output valid JSON matching the requested schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_model=ClaimsResult,
            task="extraction",
            temperature=0.15,
        )
        return result.to_claims()

    def _build_content(self, paper: Paper) -> str:
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

    @staticmethod
    def _format_methods_for_claim_prompt(methods: list[Methodology]) -> str:
        lines: list[str] = []
        for i, m in enumerate(methods):
            lines.append(f"[{i}] {m.name} ({m.category})")
            lines.append(f"    概述: {m.overview[:200]}")
            if m.innovations:
                lines.append(f"    创新: {'; '.join(m.innovations[:3])}")
            lines.append("")
        return "\n".join(lines)


# ── Pass 1 响应模型 ──────────────────────────

from pydantic import BaseModel, Field


class MethodItem(BaseModel):
    name: str
    category: str = ""
    overview: str = ""
    procedure: list[str] = Field(default_factory=list)
    key_formulas: list[str] = Field(default_factory=list)
    innovations: list[str] = Field(default_factory=list)
    inputs: str = ""
    outputs: str = ""


class MethodResult(BaseModel):
    methodologies: list[MethodItem] = Field(default_factory=list)

    def to_methods(self) -> list[Methodology]:
        import logging
        _logger = logging.getLogger(__name__)
        out: list[Methodology] = []
        for i, m in enumerate(self.methodologies):
            try:
                out.append(Methodology(
                    id=f"method-{i + 1:03d}",
                    name=m.name,
                    category=m.category,
                    overview=m.overview,
                    procedure=m.procedure,
                    key_formulas=[_strip_dollar_signs(f) for f in m.key_formulas],
                    innovations=m.innovations,
                    inputs=m.inputs,
                    outputs=m.outputs,
                ))
            except Exception as exc:
                _logger.warning(f"跳过 method-{i + 1:03d} ({m.name}): {exc}")
        return out


# ── Pass 2 响应模型 ──────────────────────────


class ClaimItem(BaseModel):
    type: str = Field(description="theoretical | empirical | comparative | design")
    problem: str = Field(description="针对/解决了什么具体问题")
    method_applied: str = Field(description="应用了什么方法或技术手段")
    mechanism: str = Field(description="为什么能解决问题，因果逻辑")
    result: str = Field(description="产生了什么效果，量化或定性")
    condition: str = Field(description="在什么假设/前提下成立，什么会导致不成立")
    assumptions: list[str] = Field(default_factory=list)
    context: str = Field(default="", description="原文支撑句")
    confidence: float = Field(default=0.5)
    related_method_indices: list[int] = Field(default_factory=list)


class ClaimsResult(BaseModel):
    claims: list[ClaimItem] = Field(default_factory=list)

    def to_claims(self) -> list[Claim]:
        import logging
        _logger = logging.getLogger(__name__)
        out: list[Claim] = []
        for i, item in enumerate(self.claims):
            claim_id = f"claim-{i + 1:03d}"
            try:
                related = [
                    f"method-{idx + 1:03d}"
                    for idx in item.related_method_indices
                ]
                out.append(Claim(
                    id=claim_id,
                    type=item.type,  # type: ignore[arg-type]
                    problem=item.problem,
                    method_applied=item.method_applied,
                    mechanism=item.mechanism,
                    result=item.result,
                    condition=item.condition,
                    context=item.context,
                    assumptions=item.assumptions,
                    confidence=item.confidence,
                    related_method_ids=related,
                ))
            except Exception as exc:
                _logger.warning(f"跳过 {claim_id}: {exc}")
        return out


def _strip_dollar_signs(s: str) -> str:
    s = s.strip()
    while s.startswith("$$") and s.endswith("$$"):
        s = s[2:-2].strip()
    while s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    return s
