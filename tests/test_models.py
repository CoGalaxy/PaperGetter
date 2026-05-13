"""核心数据模型测试."""

from paper_get_agent.models import (
    Author, PaperMeta, Section, Paper, Claim, Experiment,
    ValidationResult, Limitation, AnalysisReport,
)


def test_paper_creation():
    paper = Paper(
        meta=PaperMeta(title="测试论文"),
        sections=[Section(heading="Introduction", level=1, paragraphs=["这是引言段落。"])],
    )
    assert paper.meta.title == "测试论文"
    assert len(paper.sections) == 1


def test_claim_types():
    claim = Claim(
        id="c-001",
        type="empirical",
        statement="方法 X 在数据集 Y 上提升 5%",
        confidence=0.8,
    )
    assert claim.type.value == "empirical"


def test_report_serialization():
    report = AnalysisReport(
        paper=PaperMeta(title="测试"),
        claims=[Claim(id="c-001", type="design", statement="提出架构 A")],
    )
    d = report.model_dump_json()
    assert "c-001" in d
