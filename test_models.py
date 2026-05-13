"""测试 config.yaml 中配置的各模型连通性.

用法:
    python test_models.py                  # 测试所有模型
    python test_models.py --model deepseek-v4-pro  # 只测指定模型
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from openai import OpenAI
from rich.console import Console
from rich.table import Table
from rich.text import Text

from paper_get_agent.llm import LLMConfig

console = Console()

TEST_MESSAGE = [
    {"role": "user", "content": "用一句话回答：1+1等于几？只输出答案。"},
]

TEST_MESSAGE_JSON = [
    {"role": "user", "content": '输出纯 JSON: {"answer": 2} ，不要加任何其他文字。'},
]

# ── 测试逻辑 ──────────────────────────────


def test_chat(client: OpenAI, model: str, timeout: int = 30) -> dict:
    """测试普通对话."""
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=TEST_MESSAGE,  # type: ignore[arg-type]
            max_tokens=64,
            timeout=timeout,
        )
        elapsed = time.time() - t0
        content = resp.choices[0].message.content or ""
        return {
            "ok": True,
            "elapsed": elapsed,
            "response": content.strip(),
            "error": "",
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "ok": False,
            "elapsed": elapsed,
            "response": "",
            "error": str(e)[:300],
        }


def test_json_mode(client: OpenAI, model: str, timeout: int = 30) -> dict:
    """测试 JSON 模式 (response_format)."""
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=TEST_MESSAGE_JSON,  # type: ignore[arg-type]
            max_tokens=64,
            timeout=timeout,
            response_format={"type": "json_object"},
        )
        elapsed = time.time() - t0
        content = resp.choices[0].message.content or ""
        return {
            "ok": True,
            "elapsed": elapsed,
            "response": content.strip()[:200],
            "error": "",
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "ok": False,
            "elapsed": elapsed,
            "response": "",
            "error": str(e)[:300],
        }


def test_structured(client: OpenAI, model: str, timeout: int = 30) -> dict:
    """测试结构化输出 (prompt 注入 JSON schema + 解析)."""
    import json
    import re
    from pydantic import BaseModel

    class SimpleResult(BaseModel):
        answer: int

    schema_json = json.dumps(SimpleResult.model_json_schema(), ensure_ascii=False)
    prompt = (
        f"请严格按照以下 JSON Schema 输出，放在 ```json 代码块中:\n"
        f"```json\n{schema_json}\n```\n"
        f"只输出 JSON，不要加解释。"
    )

    t0 = time.time()
    try:
        # reasoner 模型不接受 temperature
        params: dict = dict(
            model=model,
            messages=[{"role": "user", "content": prompt}],  # type: ignore[arg-type]
            max_tokens=256,
            timeout=timeout,
        )
        if not _is_reasoner(model):
            params["temperature"] = 0.0

        resp = client.chat.completions.create(**params)
        text = resp.choices[0].message.content or ""

        # 解析 JSON
        m = re.search(r"```json\s*([\s\S]*?)```", text)
        if not m:
            m = re.search(r"```\s*([\s\S]*?)```", text)
        json_str = m.group(1).strip() if m else text.strip()
        data = SimpleResult.model_validate_json(json_str)

        elapsed = time.time() - t0
        return {
            "ok": True,
            "elapsed": elapsed,
            "response": f"answer={data.answer}",
            "error": "",
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "ok": False,
            "elapsed": elapsed,
            "response": "",
            "error": str(e)[:300],
        }


def _is_reasoner(model: str) -> bool:
    return any(kw in model.lower() for kw in ("reasoner", "v4-pro", "r1", "o1", "o3"))


# ── 入口 ──────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="测试 LLM 模型连通性")
    parser.add_argument("--model", "-m", help="只测试指定模型")
    args = parser.parse_args()

    config = LLMConfig("config.yaml")

    console.print(f"[bold]API Base:[/] {config.api_base}")
    console.print(f"[bold]API Key:[/] {'***' + config.api_key[-8:] if config.api_key else 'EMPTY'}")

    # 收集所有需要测试的模型
    if args.model:
        models_to_test = [args.model]
    else:
        models_to_test = sorted(set(config.models.values()))

    console.print(f"\n[bold]待测试模型:[/] {', '.join(models_to_test)}\n")

    client = OpenAI(
        base_url=config.api_base,
        api_key=config.api_key,
    )

    table = Table(title="模型连通性测试")
    table.add_column("模型", style="cyan", no_wrap=True)
    table.add_column("普通对话", style="white")
    table.add_column("JSON 模式", style="white")
    table.add_column("结构化输出", style="white")

    for model in models_to_test:
        console.print(f"[yellow]测试 {model}...[/]")

        # 1. 普通对话
        chat_r = test_chat(client, model)
        chat_str = _format_result(chat_r)

        # 2. JSON 模式
        json_r = test_json_mode(client, model)
        json_str = _format_result(json_r)

        # 3. 结构化输出 (LLMClient)
        struct_r = test_structured(client, model)
        struct_str = _format_result(struct_r)

        table.add_row(model, chat_str, json_str, struct_str)

        # 打印详细信息
        for label, r in [("普通对话", chat_r), ("JSON模式", json_r), ("结构化", struct_r)]:
            if not r["ok"]:
                console.print(f"  [red]{label} 失败:[/] {r['error'][:120]}")
            else:
                console.print(f"  [dim]{label}: {r['elapsed']:.1f}s → {r['response'][:80]}[/]")

    console.print("")
    console.print(table)


def _format_result(r: dict) -> str:
    if r["ok"]:
        return f"[green]✓ {r['elapsed']:.1f}s[/]"
    err = r["error"]
    # 提取关键错误信息
    if "invalid_request_error" in err or "does not support" in err:
        return "[yellow]△ 不支持[/]"
    if "401" in err or "auth" in err.lower():
        return "[red]✘ 认证失败[/]"
    if "timed out" in err.lower() or "timeout" in err.lower():
        return "[red]✘ 超时[/]"
    if "not found" in err.lower() or "404" in err:
        return "[red]✘ 模型不存在[/]"
    return f"[red]✘ 错误[/]"


if __name__ == "__main__":
    main()
