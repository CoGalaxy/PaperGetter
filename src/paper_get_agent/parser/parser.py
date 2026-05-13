"""论文 PDF 解析器.

将 PDF 转换为结构化的 Paper 对象，包含章节切分、表格提取.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from ..models.paper import Paper, PaperMeta, Section
from ..llm.client import LLMClient


class PaperParser:
    """PDF 论文解析器."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm

    def parse(self, file_path: str | Path, on_progress=None) -> Paper:
        """解析 PDF 论文，返回结构化 Paper 对象."""
        file_path = Path(file_path)
        progress = on_progress or (lambda p, s, d, e: None)

        progress("parse", "step", "打开 PDF 文件...", 0)
        doc = fitz.open(str(file_path))
        n_pages = len(doc)

        # 1. 提取全文文本
        full_text_parts: list[str] = []
        for i, page in enumerate(doc):
            full_text_parts.append(page.get_text("text"))
            if (i + 1) % 5 == 0 or i == n_pages - 1:
                progress("parse", "step", f"提取文本: {i + 1}/{n_pages} 页", 0)
        raw_text = "\n\n".join(full_text_parts)

        # 2. 提取元信息（PDF metadata + LLM 补充）
        progress("parse", "step", "提取论文元信息...", 0)
        meta = self._extract_meta(doc, raw_text, file_path)

        # 3. 章节切分
        progress("parse", "step", "切分章节...", 0)
        sections = self._split_sections(raw_text)
        progress("parse", "step", f"识别到 {len(sections)} 个章节", 0)

        # 4. 提取表格（PyMuPDF 原生支持）
        try:
            table_records = self._extract_tables(doc)
            self._attach_tables(sections, table_records)
            if table_records:
                progress("parse", "step", f"提取了 {len(table_records)} 个表格", 0)
        except Exception:
            pass

        doc.close()

        return Paper(meta=meta, sections=sections, raw_text=raw_text)

    # ── 内部方法 ────────────────────────────

    def _extract_meta(self, doc: fitz.Document, raw_text: str, file_path: Path) -> PaperMeta:
        """从 PDF metadata 和文本中提取论文元信息."""
        pdf_meta = doc.metadata or {}

        # 先尝试从 PDF 元信息中拿
        title = pdf_meta.get("title", "")
        authors_raw = pdf_meta.get("author", "")

        # 前 2000 字符通常包含标题和作者
        head = raw_text[:2000]

        # 用规则提取标题（第一行非空文本）
        if not title:
            lines = [l.strip() for l in head.split("\n") if l.strip()]
            title = lines[0] if lines else file_path.stem

        # 用正则提取 arxiv ID
        arxiv_id: str | None = None
        m = re.search(r"arXiv[:\s]*(\d{4}\.\d{4,5})", raw_text[:3000], re.IGNORECASE)
        if m:
            arxiv_id = m.group(1)

        return PaperMeta(
            title=title[:300],
            authors=[],
            arxiv_id=arxiv_id,
            source_path=str(file_path),
            abstract=self._extract_abstract(raw_text),
        )

    def _extract_abstract(self, text: str) -> str:
        """用规则提取摘要."""
        m = re.search(
            r"(?:abstract|摘要)\s*[—\-:]*\s*(.+?)(?:\n(?:1\.?\s|I[. ]|\bIntroduction\b|\b引言\b))",
            text[:5000],
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()[:2000]
        return ""

    def _split_sections(self, text: str) -> list[Section]:
        """将文本按标题切分为章节.

        支持中英文常见标题模式:
          - 1. / 1.1 / 1.1.1 式编号标题
          - I. / A. / (a) 式标题
          - Introduction / Method / Related Work 等
          - 引言 / 方法 / 相关工作 等中文标题
        """
        # 标题模式（英文 + 中文）
        patterns = [
            # 编号标题: "1. Introduction" / "2.1 方法"
            r"^(?:\d+\.?)+\s+\w[\w\s]*$",
            # 英文标题: "Introduction", "Related Work"
            r"^(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,6})$",
            # 中文标题: "引言"
            r"^(?:[一-鿿][一-鿿\s]{1,20})$",
        ]
        section_re = re.compile("|".join(f"({p})" for p in patterns), re.MULTILINE)

        lines = text.split("\n")
        headings: list[tuple[int, str]] = []  # (line_index, heading_text)

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or len(stripped) > 120:
                continue
            if section_re.match(stripped):
                headings.append((i, stripped))

        if not headings:
            # 无法识别标题，整篇作为一个 section
            return [Section(heading="全文", level=1, paragraphs=_clean_paragraphs(lines))]

        sections: list[Section] = []
        for j, (line_idx, heading) in enumerate(headings):
            next_idx = headings[j + 1][0] if j + 1 < len(headings) else len(lines)
            body_lines = lines[line_idx + 1 : next_idx]
            sections.append(
                Section(
                    heading=heading,
                    level=self._guess_level(heading),
                    paragraphs=_clean_paragraphs(body_lines),
                )
            )

        return sections

    @staticmethod
    def _guess_level(heading: str) -> int:
        """根据编号格式猜测标题层级."""
        if re.match(r"^\d+\.\d+\.\d+", heading):
            return 3
        if re.match(r"^\d+\.\d+", heading):
            return 2
        return 1

    def _extract_tables(self, doc: fitz.Document) -> list[dict]:
        """用 PyMuPDF 提取所有表格."""
        tables: list[dict] = []
        for page_num, page in enumerate(doc):
            for tab in page.find_tables().tables:
                rows = [[cell.get_text(strip=True) for cell in row] for row in tab.extract()]
                tables.append({"page": page_num, "rows": rows})
        return tables

    @staticmethod
    def _attach_tables(sections: list[Section], tables: list[dict]) -> None:
        """将表格附加到最近的 section（简单策略: 放入第一个 section）."""
        # 后续可用 LLM 做精细匹配；目前简单归入正文
        if sections:
            sections[0].tables.extend(tables)


def _clean_paragraphs(lines: list[str]) -> list[str]:
    """清理行列表，合并为段落."""
    paras: list[str] = []
    buf: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            buf.append(stripped)
        elif buf:
            paras.append(" ".join(buf))
            buf = []
    if buf:
        paras.append(" ".join(buf))
    return [p for p in paras if len(p) > 30]  # 过滤太短的噪音行
