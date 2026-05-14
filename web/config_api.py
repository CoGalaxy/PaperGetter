"""配置读写 API — 将 config.yaml 映射为 JSON + Pydantic 校验."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


# ── 校验模型 ──────────────────────────────

class LLMModelAssign(BaseModel):
    extraction: str = "deepseek-v4-pro"
    code_generation: str = "deepseek-v4-flash"
    parsing: str = "deepseek-v4-flash"
    comparison: str = "deepseek-v4-flash"
    limitation: str = "deepseek-v4-pro"
    summarization: str = "deepseek-v4-pro"


class LLMDefaults(BaseModel):
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=256, le=65536)
    timeout: int = Field(default=120, ge=10, le=600)


class LLMSection(BaseModel):
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    models: LLMModelAssign = Field(default_factory=LLMModelAssign)
    defaults: LLMDefaults = Field(default_factory=LLMDefaults)


class ParserSection(BaseModel):
    engine: Literal["pymupdf", "marker"] = "pymupdf"
    extract_figures: bool = False
    extract_tables: bool = True
    chunk_size: int = Field(default=4000, ge=500, le=32000)


class SandboxSection(BaseModel):
    engine: Literal["docker", "subprocess", "e2b"] = "docker"
    image: str = "python:3.11-slim"
    timeout: int = Field(default=60, ge=10, le=600)
    memory_limit: str = "512m"
    network: Literal["none", "bridge"] = "none"


class ConfigSchema(BaseModel):
    llm: LLMSection
    parser: ParserSection = Field(default_factory=ParserSection)
    sandbox: SandboxSection = Field(default_factory=SandboxSection)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


# ── API 函数 ──────────────────────────────

def get_config() -> dict:
    """读取 config.yaml 返回 JSON，API key 脱敏."""
    raw = _load_raw()
    # 脱敏 api_key
    if "llm" in raw and "api_key" in raw["llm"]:
        key = raw["llm"]["api_key"]
        if key and len(key) > 8:
            raw["llm"]["api_key"] = key[:4] + "****" + key[-4:]
    return raw


def update_config(data: dict) -> dict:
    """校验并写入 config.yaml，返回更新后的脱敏配置."""
    validated = ConfigSchema(**data)
    raw = validated.model_dump()

    # 保留已有的 api_key（如果前端没传完整 key）
    existing = _load_raw()
    existing_key = existing.get("llm", {}).get("api_key", "")
    new_key = data.get("llm", {}).get("api_key", "")

    if new_key and "****" in new_key:
        # 未被修改的脱敏 key，保留原值
        raw["llm"]["api_key"] = existing_key
    elif new_key:
        raw["llm"]["api_key"] = new_key
    else:
        raw["llm"]["api_key"] = existing_key

    _save_raw(raw)
    return get_config()


def _load_raw() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_raw(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
