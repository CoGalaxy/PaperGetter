"""LLM 客户端抽象层.

通过 OpenAI 兼容接口对接国产模型（DeepSeek / Qwen / Kimi）.
DeepSeek reasoner/pro 模型不支持 tool_choice 和 response_format,
因此结构化输出采用 prompt-engineering + JSON 解析策略.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from openai import OpenAI


class LLMConfig:
    """管理多模型配置."""

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        raw = self._load_config(config_path)
        llm_cfg = raw.get("llm", {})

        self.api_base = os.path.expandvars(llm_cfg.get("api_base", "https://api.deepseek.com/v1"))
        self.api_key = os.path.expandvars(llm_cfg.get("api_key", ""))
        self.models: dict[str, str] = llm_cfg.get("models", {})
        self.defaults: dict[str, Any] = llm_cfg.get("defaults", {})

    @staticmethod
    def _load_config(path: str | Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


class LLMClient:
    """OpenAI 兼容的 LLM 客户端, 支持按任务自动切换模型.

    结构化输出策略:
    - reasoner/pro 类模型 (deepseek-reasoner, deepseek-v4-pro 等):
      prompt 中注入 JSON schema, 从文本回复中提取 JSON
    - 通用模型 (deepseek-chat, qwen, kimi 等):
      使用 response_format={"type": "json_object"}
    """

    # 不支持 tool_choice / response_format 的模型关键词
    REASONER_KEYWORDS = ("reasoner", "v4-pro", "r1", "o1", "o3")

    def __init__(
        self,
        config: LLMConfig | None = None,
        config_path: str | Path = "config.yaml",
    ) -> None:
        self.config = config or LLMConfig(config_path)
        self._client = OpenAI(
            base_url=self.config.api_base,
            api_key=self.config.api_key,
        )

    @property
    def client(self) -> OpenAI:
        return self._client

    def get_model(self, task: str) -> str:
        """获取指定任务对应的模型名."""
        return self.config.models.get(task, "deepseek-chat")

    def _is_reasoner(self, model: str) -> bool:
        """判断是否为推理类模型（不支持结构化输出特性）."""
        lower = model.lower()
        return any(kw in lower for kw in self.REASONER_KEYWORDS)

    # ── 普通对话 ────────────────────────────

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        task: str = "extraction",
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """发送对话请求，返回文本响应."""
        model = self.get_model(task)
        params: dict[str, Any] = dict(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens or self.config.defaults.get("max_tokens", 4096),
        )
        # reasoner 模型不接受 temperature
        if not self._is_reasoner(model):
            params["temperature"] = temperature or self.config.defaults.get("temperature", 0.1)
        params.update(kwargs)

        resp = self._client.chat.completions.create(**params)
        return resp.choices[0].message.content or ""

    # ── 结构化输出 ──────────────────────────

    def structured(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        *,
        task: str = "extraction",
        max_retries: int = 2,
        **kwargs: Any,
    ) -> Any:
        """以 Pydantic 模型返回结构化数据.

        自动根据模型类型选择策略:
        - reasoner 模型 → prompt 注入 schema → 正则提取 JSON → 解析
        - 通用模型 → response_format json_object → JSON 解析
        """
        model = self.get_model(task)

        if self._is_reasoner(model):
            return self._structured_reasoner(messages, response_model, model, max_retries, **kwargs)
        return self._structured_normal(messages, response_model, model, max_retries, **kwargs)

    def _structured_reasoner(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        model: str,
        max_retries: int,
        **kwargs: Any,
    ) -> Any:
        """Reasoner 模型: 在 prompt 中注入 JSON schema, 从文本提取 JSON."""
        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False, indent=2)

        msgs = [dict(m) for m in messages]
        last = msgs[-1]
        last["content"] = (
            f"{last['content']}\n\n"
            f"请严格按照以下 JSON Schema 输出，放在 ```json 代码块中，不要输出其他内容：\n"
            f"```json\n{schema_json}\n```"
        )

        # reasoner 模型可能需要更多 tokens（推理链 + JSON）
        kwargs.setdefault("max_tokens", 16384)

        last_error = None
        last_text = ""
        for attempt in range(max_retries + 1):
            try:
                last_text = self._chat_raw(model, msgs, **kwargs)
                return self._parse_json_response(last_text, response_model)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    msgs.append({"role": "assistant", "content": last_text[:500]})
                    msgs.append({
                        "role": "user",
                        "content": (
                            f"上次输出的 JSON 解析失败 ({e})。"
                            f"请严格按照 Schema 重新输出完整 JSON，放在 ```json 代码块中。"
                            f"确保 JSON 结束后有 ``` 闭合标记。"
                        ),
                    })

        tail = last_text[-300:] if len(last_text) > 300 else last_text
        raise ValueError(f"JSON 解析失败 ({max_retries + 1} 次尝试): {last_error}; 响应末尾: {tail}") from last_error

    def _structured_normal(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        model: str,
        max_retries: int,
        **kwargs: Any,
    ) -> Any:
        """通用模型: 使用 response_format json_object, 失败时反馈错误重试."""
        msgs = [dict(m) for m in messages]
        last = msgs[-1]
        last["content"] = f"{last['content']}\n\n请输出纯 JSON，不要加 markdown 代码块。"

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                text = self._chat_raw(
                    model,
                    msgs,
                    response_format={"type": "json_object"},
                    **kwargs,
                )
                return response_model.model_validate_json(text)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    msgs.append({"role": "assistant", "content": "[JSON 解析失败]"})
                    msgs.append({
                        "role": "user",
                        "content": (
                            f"上次输出的 JSON 解析失败 ({e})。"
                            f"请严格按照要求输出纯 JSON，不要加 markdown 代码块。"
                        ),
                    })

        # 所有重试耗尽，退回 reasoner 策略
        try:
            return self._structured_reasoner(messages, response_model, model, 0, **kwargs)
        except Exception as reasoner_err:
            raise ValueError(
                f"JSON 解析失败 (normal + reasoner 均失败): {last_error}; reasoner: {reasoner_err}"
            ) from reasoner_err

    def _chat_raw(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        """底层 API 调用，不做任何包装."""
        params: dict[str, Any] = dict(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=kwargs.pop("max_tokens", self.config.defaults.get("max_tokens", 4096)),
        )
        if not self._is_reasoner(model):
            params["temperature"] = kwargs.pop("temperature", self.config.defaults.get("temperature", 0.1))
        params.update(kwargs)

        resp = self._client.chat.completions.create(**params)
        return resp.choices[0].message.content or ""

    @staticmethod
    def _parse_json_response(text: str, response_model: type) -> Any:
        """从模型回复中提取 JSON 并解析为 Pydantic 模型.

        处理多种情况: code fence, 截断响应, 裸 JSON, 等等.
        """
        # 策略 1: ```json ... ``` (带标注的完整 code block)
        m = re.search(r"```json\s*([\s\S]*?)```", text)
        if m:
            return response_model.model_validate_json(m.group(1).strip())

        # 策略 2: ``` ... ``` (无标注 code block)
        m = re.search(r"```\s*([\s\S]*?)```", text)
        if m:
            return response_model.model_validate_json(m.group(1).strip())

        # 策略 3: ```json 开头但缺少闭合 ``` (响应被截断)
        m = re.search(r"```json\s*([\s\S]*)", text)
        if m:
            json_str = m.group(1).strip()
            json_str = LLMClient._try_fix_truncated_json(json_str)
            return response_model.model_validate_json(json_str)

        # 策略 4: 查找第一个 { 到最后一个 } 之间的内容
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            return response_model.model_validate_json(text[first_brace:last_brace + 1])

        # 策略 5: 整个文本就是 JSON
        try:
            return response_model.model_validate_json(text.strip())
        except Exception:
            tail = text[-300:] if len(text) > 300 else text
            raise ValueError(f"无法从 LLM 回复中提取 JSON，响应末尾: {tail}")

    @staticmethod
    def _try_fix_truncated_json(json_str: str) -> str:
        """尝试修复被截断的 JSON: 补全缺失的 } 和 ]."""
        # 统计未闭合的括号
        open_braces = json_str.count("{") - json_str.count("}")
        open_brackets = json_str.count("[") - json_str.count("]")

        # 移除末尾不完整的键值对
        # 找到最后一个完整的逗号或引号位置
        if json_str.rstrip().endswith(","):
            json_str = json_str.rstrip()[:-1]

        # 补全缺失的闭合符号
        json_str = json_str.rstrip()
        if open_brackets > 0:
            json_str += "]" * open_brackets
        if open_braces > 0:
            json_str += "}" * open_braces

        return json_str
