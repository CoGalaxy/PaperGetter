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

        优先用 LLM 识别标题（准确、理解上下文），不可用时回退到正则.
        """
        lines = text.split("\n")

        # 尝试 LLM 识别
        if self.llm is not None:
            try:
                headings = self._llm_detect_headings(lines)
                if headings:
                    return self._build_sections(lines, headings)
            except Exception:
                pass  # LLM 失败，回退正则

        # 回退：正则匹配
        headings = self._regex_detect_headings(lines)
        return self._build_sections(lines, headings)

    # ── LLM 标题识别 ────────────────────────

    HEADING_DETECTION_PROMPT = """你是一个 PDF 解析器。以下是从一篇学术论文中提取的候选行（每行格式: "行号|内容"）。

请标注哪些行是真正的**章节标题**（section/subsection heading），并给出层级。

判断标准:
- 编号标题: "1. Introduction", "2.1 Method", "3.1.1 Data Preprocessing" → 是标题
- 英文名词短语: "Related Work", "Experimental Setup", "Performance Comparison" → 是标题
- 中文短语: "引言", "相关工作", "实验设置" → 是标题
- 全大写的短行: "ABSTRACT", "INTRODUCTION", "CONCLUSION" → 是标题
- 论文组成部分: "Abstract", "References", "Acknowledgments" → 是标题
- 普通句子、数据行、公式、编号列表项(如 "1) xxx") → 不是标题
- 论文中的变量定义行、单独的数字行 → 不是标题

层级定义:
- level 1: 一级标题 (如 "1. Introduction", "INTRODUCTION", "引言")
- level 2: 二级标题 (如 "2.1 Method", "A. Related Work")
- level 3: 三级及以下 (如 "2.1.1 Details")

请输出 JSON，只包含被判定为标题的行:
```json
{
  "headings": [
    {"line": 行号, "text": "标题原文", "level": 1-3}
  ]
}
```

候选行:
---
{candidates}
---"""

    def _llm_detect_headings(self, lines: list[str]) -> list[tuple[int, str, int]]:
        """用 LLM 从文本行中识别章节标题."""
        # 1. 收集候选行：短行、在文本块之间、首字母大写或数字开头
        candidates: list[tuple[int, str]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or len(stripped) > 150:
                continue
            # 过滤明显是正文句子的行（以小写字母开头）
            if stripped[0].islower():
                continue
            # 过滤纯数字或纯符号行
            if re.match(r'^[\d\s\.\-–—,;:!?()\[\]{}⟨⟩]+$', stripped):
                continue
            # 优先选择前后有空行的行（更可能是标题）
            prev_blank = i == 0 or not lines[i - 1].strip()
            next_blank = i == len(lines) - 1 or not lines[i + 1].strip()
            if prev_blank or next_blank or len(stripped) < 60:
                candidates.append((i, stripped))

        if not candidates:
            return []

        # 2. 构建批量 prompt（控制 token 量，最多发 200 条候选）
        if len(candidates) > 200:
            # 优先保留更可能是标题的：前后有空行的、更短的
            candidates.sort(key=lambda x: (
                not (x[0] == 0 or not lines[x[0] - 1].strip()),  # 前面有空行优先
                len(x[1]),  # 短行优先
            ))
            candidates = candidates[:200]
            candidates.sort(key=lambda x: x[0])  # 恢复行号顺序

        candidate_text = "\n".join(
            f"{idx:04d}|{text}" for idx, text in candidates
        )

        # 3. 调用 LLM
        result = self.llm.structured(
            messages=[
                {"role": "user", "content": self.HEADING_DETECTION_PROMPT.format(candidates=candidate_text)},
            ],
            response_model=HeadingDetectionResult,
            task="parsing",
            temperature=0.0,
        )

        # 4. 转换结果
        headings: list[tuple[int, str, int]] = []
        for h in result.headings:
            headings.append((h.line, h.text, h.level))
        return headings

    # ── 回退: 正则标题识别 ──────────────────

    @staticmethod
    def _regex_detect_headings(lines: list[str]) -> list[tuple[int, str, int]]:
        """正则匹配标题（LLM 不可用时的回退）."""
        # 白名单: 只匹配已知论文章节名
        known_headings = (
            r"abstract|introduction|related\s*work|background|preliminar|"
            r"method|proposed|approach|model|architecture|framework|"
            r"experiment|evaluation|result|discussion|analysis|"
            r"ablation|comparison|baseline|setup|implementation|"
            r"conclusion|future\s*work|limitation|discussion|summary|"
            r"acknowledgment|reference|bibliography|appendix|supplementary|"
            r"abstract|摘要|引言|绪论|背景|相关工作|文献综述|"
            r"方法|模型|架构|框架|算法|设计|"
            r"实验|评估|结果|分析|讨论|"
            r"消融|对比|基线|实施|实现|"
            r"结论|展望|局限|不足|总结|"
            r"致谢|参考文献|附录|补充"
        )
        # 编号 + 已知标题: "1. Introduction", "2.1 Method"
        numbered_heading = re.compile(
            rf"^(?:[\d]+\.?)*\s*({known_headings})\s*$",
            re.IGNORECASE,
        )
        # 纯已知标题: "Introduction", "Related Work"
        named_heading = re.compile(
            rf"^\s*({known_headings})\s*$",
            re.IGNORECASE,
        )
        # 全大写短行: "ABSTRACT", "INTRODUCTION"
        allcaps_heading = re.compile(r"^[A-Z][A-Z\s\-–—]{2,40}$")

        headings: list[tuple[int, str, int]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or len(stripped) > 100:
                continue

            m = numbered_heading.match(stripped)
            if m:
                level = PaperParser._guess_level(stripped)
                headings.append((i, stripped, level))
                continue

            m = named_heading.match(stripped)
            if m:
                # 纯标题名，常见于无编号论文
                h = stripped.lower()
                if h in ("abstract", "references", "acknowledgments", "appendix", "conclusion"):
                    headings.append((i, stripped, 1))
                else:
                    headings.append((i, stripped, 2))
                continue

            m = allcaps_heading.match(stripped)
            if m:
                headings.append((i, stripped, 1))
                continue

        return headings

    # ── 根据标题构建 Section 列表 ────────────

    @staticmethod
    def _build_sections(
        lines: list[str], headings: list[tuple[int, str, int]]
    ) -> list[Section]:
        """根据识别出的标题和原文行，构建 Section 列表."""
        if not headings:
            return [Section(heading="全文", level=1, paragraphs=_clean_paragraphs(lines))]

        sections: list[Section] = []
        for j, (line_idx, heading, level) in enumerate(headings):
            next_idx = headings[j + 1][0] if j + 1 < len(headings) else len(lines)
            body_lines = lines[line_idx + 1 : next_idx]
            sections.append(
                Section(
                    heading=heading,
                    level=level,
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


# ── LLM 标题检测辅助模型 ────────────────────

from pydantic import BaseModel, Field


class HeadingItem(BaseModel):
    line: int = Field(description="行号（候选行中的四位编号）")
    text: str = Field(description="标题原文")
    level: int = Field(default=1, description="层级 1-3")


class HeadingDetectionResult(BaseModel):
    headings: list[HeadingItem] = Field(default_factory=list)
