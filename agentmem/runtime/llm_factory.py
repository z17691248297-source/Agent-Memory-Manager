from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

from agentmem.runtime.llm_client import OpenAICompatibleClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_runtime_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """读取运行配置；只依赖本地 config 文件，不访问网络。"""
    path = Path(config_path) if config_path else PROJECT_ROOT / "configs" / "config.yaml"
    if not path.exists():
        return {"llm": {"backend": "vllm"}}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        return dict(data)
    except Exception:
        try:
            data = json.loads(text)
            return dict(data) if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
        return _parse_simple_yaml(text)


def build_llm_client(config_path: str | Path | None = None):
    """按配置构造 LLM client。

    支持：
    - vllm：本地 vLLM OpenAI-compatible 服务。
    - openai_compatible/openai：模型厂商 OpenAI-compatible API。

    环境变量优先级高于 config：
    - AGENTMEM_LLM_BACKEND
    - AGENTMEM_LLM_BASE_URL
    - AGENTMEM_MODEL
    - AGENTMEM_API_KEY
    """
    config = load_runtime_config(config_path)
    llm_config = dict(config.get("llm") or {})
    backend = os.getenv("AGENTMEM_LLM_BACKEND", str(llm_config.get("backend", "vllm"))).lower()

    if backend in {"vllm", "openai", "openai_compatible", "openai-compatible"}:
        default_base_url = "http://localhost:8000/v1" if backend == "vllm" else "https://api.openai.com/v1"
        base_url = (
            os.getenv("AGENTMEM_LLM_BASE_URL")
            or llm_config.get("base_url")
            or llm_config.get("vllm_base_url")
            or default_base_url
        )
        model = os.getenv("AGENTMEM_MODEL") or llm_config.get("model") or "Qwen/Qwen2.5-7B-Instruct"
        api_key = _resolve_api_key(llm_config, backend)
        return OpenAICompatibleClient(
            base_url=str(base_url),
            api_key=api_key,
            model=str(model),
            temperature=float(llm_config.get("temperature", 0.2)),
            max_tokens=int(llm_config.get("max_tokens", 512)),
            timeout=float(llm_config.get("timeout", 120)),
            stream=backend == "vllm",
            max_retries=int(llm_config.get("max_retries", 2)),
        )

    raise ValueError(f"不支持的 llm.backend: {backend}")


def _resolve_api_key(llm_config: dict[str, Any], backend: str) -> str:
    if os.getenv("AGENTMEM_API_KEY"):
        return str(os.getenv("AGENTMEM_API_KEY"))
    api_key_env = llm_config.get("api_key_env")
    if api_key_env and os.getenv(str(api_key_env)):
        return str(os.getenv(str(api_key_env)))
    if llm_config.get("api_key"):
        return str(llm_config["api_key"])
    return "EMPTY" if backend == "vllm" else ""


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_key = line[:-1].strip()
            result[current_key] = {}
            continue
        if current_key and ":" in line:
            key, value = line.strip().split(":", 1)
            result[current_key][key.strip()] = _parse_scalar(value.strip())
    return result


def _parse_scalar(value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value
