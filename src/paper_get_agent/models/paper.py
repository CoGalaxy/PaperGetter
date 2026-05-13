"""核心数据模型定义."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ────────────────────────────────────────────
# 论文元信息
# ────────────────────────────────────────────

class Author(BaseModel):
    name: str
    affiliation: str | None = None
    email: str | None = None


class PaperMeta(BaseModel):
    title: str
    authors: list[Author] = Field(default_factory=list)
    venue: str | None = None
    year: int | None = None
    arxiv_id: str | None = None
    doi: str | None = None
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    source_path: str = ""  # 原始 PDF 路径


# ────────────────────────────────────────────
# 结构化文档
# ────────────────────────────────────────────

class Section(BaseModel):
    """论文的一个章节."""
    heading: str
    level: int = 1  # 1=h1, 2=h2, ...
    paragraphs: list[str] = Field(default_factory=list)
    tables: list[dict] = Field(default_factory=list)   # {caption, rows}
    figures: list[dict] = Field(default_factory=list)   # {caption, bbox}
    equations: list[str] = Field(default_factory=list)  # LaTeX strings
    subsections: list["Section"] = Field(default_factory=list)


class Paper(BaseModel):
    """解析后的完整论文结构化表示."""
    meta: PaperMeta
    sections: list[Section] = Field(default_factory=list)
    raw_text: str = ""


# ────────────────────────────────────────────
# 观点与主张
# ────────────────────────────────────────────

class ClaimType(str, Enum):
    THEORETICAL = "theoretical"       # 数学证明、定理、理论分析
    EMPIRICAL = "empirical"           # 实验验证、数值结果
    COMPARATIVE = "comparative"       # 与 baselines 的对比
    DESIGN = "design"                  # 架构/算法设计决策


class Claim(BaseModel):
    id: str = ""  # 自动生成，如 claim-001
    type: ClaimType
    statement: str                     # 一句话概括主张
    context: str = ""                  # 原文中的上下文段落
    assumptions: list[str] = Field(default_factory=list)  # 隐含假设
    supporting_sections: list[str] = Field(default_factory=list)  # 原文支撑段落的 heading
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)  # 模型对该主张可靠性的初步判断
    method_desc: str = ""              # 如果涉及实现，描述方法步骤


class Experiment(BaseModel):
    claim_id: str
    dataset: str
    baselines: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    reported_result: str = ""          # 论文中报告的结果（数值/文字）
    setup_desc: str = ""               # 实验设置描述


# ────────────────────────────────────────────
# 方法论
# ────────────────────────────────────────────

class Methodology(BaseModel):
    """论文提出的具体方法/算法/框架."""
    id: str = ""
    name: str                          # 方法名称，如 "DeepFM Network"
    category: str = ""                 # 归类: "模型架构" / "损失函数" / "数据预处理" / "训练策略" / "评估框架"
    overview: str = ""                 # 一段话概述该方法
    procedure: list[str] = Field(default_factory=list)   # 具体步骤 (1. 2. 3. ...)
    key_formulas: list[str] = Field(default_factory=list)  # 关键公式（LaTeX）
    innovations: list[str] = Field(default_factory=list)   # 与已有方法的区别（创新点）
    inputs: str = ""                   # 方法接受什么输入
    outputs: str = ""                  # 方法产出什么输出
    related_claim_ids: list[str] = Field(default_factory=list)


# ────────────────────────────────────────────
# 验证结果
# ────────────────────────────────────────────

class Verdict(str, Enum):
    SUPPORTED = "supported"             # 验证结果支持论文主张
    PARTIALLY_SUPPORTED = "partially_supported"
    NOT_SUPPORTED = "not_supported"     # 验证结果与主张不一致
    UNVERIFIABLE = "unverifiable"       # 无法通过代码验证（纯理论等）
    ERROR = "error"                     # 验证过程出错


class ValidationResult(BaseModel):
    claim_id: str
    verdict: Verdict
    generated_code: str = ""           # 生成的验证代码（Python）
    execution_output: str = ""         # 代码执行 stdout/stderr
    evidence: str = ""                 # LLM 对照结论（为什么支持/不支持）
    toy_scenario: str = ""             # 描述用来验证的简化场景


# ────────────────────────────────────────────
# 局限性
# ────────────────────────────────────────────

class LimitationCategory(str, Enum):
    METHOD = "method"                   # 方法本身的局限性
    EXPERIMENT = "experiment"           # 实验设计的不足
    THEORY = "theory"                   # 理论证明的 gap
    REPRODUCIBILITY = "reproducibility" # 可复现性问题
    GENERALIZATION = "generalization"   # 泛化性/外部效度
    ETHICS = "ethics"                   # 伦理/公平性问题


class Limitation(BaseModel):
    category: LimitationCategory
    description: str                    # 局限性描述
    severity: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    related_claim_ids: list[str] = Field(default_factory=list)
    suggested_fix: str = ""             # 如果是可修复的，给出建议


# ────────────────────────────────────────────
# 最终报告
# ────────────────────────────────────────────

class AnalysisReport(BaseModel):
    paper: PaperMeta
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    methodologies: list[Methodology] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    validations: list[ValidationResult] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    overall_score: float = Field(default=0.0, ge=0.0, le=10.0)  # 论文综合评分
    summary: str = ""                   # 一两段总结
