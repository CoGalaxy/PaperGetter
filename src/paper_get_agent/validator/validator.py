"""轻量级观点验证器.

为每条 claim 生成靶向验证代码，在沙箱中执行，对照结果给出判断.
"""

from __future__ import annotations

import textwrap

from ..models.paper import Claim, ValidationResult, Verdict
from ..llm.client import LLMClient
from ..sandbox.sandbox import CodeSandbox


CODE_GENERATION_PROMPT = """你是一位严谨的研究者，需要为一个学术观点编写验证代码。

观点类型: {claim_type}
观点陈述: {statement}
相关上下文: {context}
预设前提: {assumptions}

请撰写一段 Python 代码来验证这个观点。
要求:
1. 构造一个最小化的 toy scenario（能验证核心逻辑即可）
2. 使用 numpy/matplotlib 等标准库
3. 输出清晰的结论（用 print 输出对比结果）
4. 代码应该能在 30 秒内执行完毕
5. 不需要 GPU，纯 CPU 即可
6. 如果需要数据，用代码生成合成数据

只输出 Python 代码，不要解释。"""

COMPARISON_PROMPT = """你是一位论文审稿人。请对比论文主张与实际验证结果，给出判断。

论文主张: {statement}

验证代码:
---
{code}
---

执行输出:
---
{output}
---

请根据执行输出来判断:
- 如果输出明确支持该主张 → "supported"
- 如果部分支持但有出入 → "partially_supported"
- 如果与主张明显矛盾 → "not_supported"
- 如果输出无法用来验证主张 → "unverifiable"

给出你的判断和简要理由。"""


class ClaimValidator:
    """为 claim 生成玩具代码并执行验证."""

    def __init__(self, llm: LLMClient, sandbox: CodeSandbox) -> None:
        self.llm = llm
        self.sandbox = sandbox

    def validate(self, claim: Claim, on_progress=None) -> ValidationResult:
        """对单条 claim 执行完整验证流程."""
        progress = on_progress or (lambda p, s, d, e: None)

        # 1. 生成验证代码
        progress("validate", "sub", f"{claim.id}: 生成验证代码...", 0)
        code = self._generate_code(claim)

        # 2. 沙箱执行
        progress("validate", "sub", f"{claim.id}: 沙箱执行中...", 0)
        output = self.sandbox.run(code)

        # 3. LLM 对照结果
        progress("validate", "sub", f"{claim.id}: LLM 对照结果...", 0)
        verdict, evidence = self._compare(claim, code, output)

        return ValidationResult(
            claim_id=claim.id,
            verdict=verdict,
            generated_code=code,
            execution_output=output,
            evidence=evidence,
            toy_scenario=f"针对主张「{claim.statement[:80]}...」的 toy 验证",
        )

    def _generate_code(self, claim: Claim) -> str:
        """用 LLM 生成验证代码."""
        prompt = CODE_GENERATION_PROMPT.format(
            claim_type=claim.type.value,
            statement=claim.statement,
            context=claim.context[:500] or "无",
            assumptions="; ".join(claim.assumptions) if claim.assumptions else "无",
        )
        code = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            task="code_generation",
            temperature=0.1,
        )
        # 清理 markdown code fence
        code = textwrap.dedent(code)
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        return code.strip()

    def _compare(self, claim: Claim, code: str, output: str) -> tuple[Verdict, str]:
        """让 LLM 对比主张和执行结果."""
        prompt = COMPARISON_PROMPT.format(
            statement=claim.statement,
            code=code,
            output=output[:2000],
        )

        # 这个阶段用简单 chat，不需要 structured output
        raw = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            task="comparison",
            temperature=0.0,
        )

        # 解析 verdict
        verdict = Verdict.UNVERIFIABLE
        if "supported" in raw.lower() and "not_supported" not in raw.lower() and "partially" not in raw.lower():
            verdict = Verdict.SUPPORTED
        elif "partially" in raw.lower():
            verdict = Verdict.PARTIALLY_SUPPORTED
        elif "not_supported" in raw.lower():
            verdict = Verdict.NOT_SUPPORTED

        return verdict, raw
