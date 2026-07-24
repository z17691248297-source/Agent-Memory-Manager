from __future__ import annotations

from pathlib import Path
from typing import Any

from agentmem.config import ConfigError, load_config, resolve_api_key
from agentmem.runtime.llm_client import OpenAICompatibleClient
from agentmem.vllm.agent_meta import AgentMetaBuilder


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_runtime_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Read runtime config with environment placeholder expansion.

    This function intentionally does not validate required endpoints so
    read-only commands and tests can inspect config templates without exporting
    model environment variables. Runtime client construction validates.
    """
    return load_config(config_path or PROJECT_ROOT / "configs" / "config.yaml", validate=False)


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
    # Client construction validates the LLM-facing fields it needs, but does
    # not require unrelated benchmark/agent defaults. That keeps old minimal
    # test configs usable while release validation remains strict elsewhere.
    config = load_config(config_path or PROJECT_ROOT / "configs" / "config.yaml", validate=False)
    llm_config = dict(config.get("llm") or {})
    vllm_config = dict(config.get("vllm") or {})
    backend = str(llm_config.get("backend", "vllm")).replace("-", "_").lower()

    if backend in {"vllm", "openai", "openai_compatible"}:
        base_url = llm_config.get("base_url") or llm_config.get("vllm_base_url")
        model = llm_config.get("model")
        if not model:
            raise ConfigError("llm.model is required")
        if not _valid_http_url(str(base_url or "")):
            raise ConfigError("llm.base_url must be a valid http(s) URL")
        api_key = resolve_api_key(llm_config)
        if not api_key and backend == "vllm":
            api_key = "EMPTY"
        enable_agent_meta = (
            _bool(vllm_config.get("enable_agent_meta", False))
            if backend == "vllm"
            else False
        )
        agent_meta_builder = None
        if enable_agent_meta:
            agent_meta_builder = AgentMetaBuilder(
                agent_id=str(vllm_config.get("agent_id", "agentmem_benchmark")),
                default_ttl=int(vllm_config.get("default_ttl", 300)),
            )
        return OpenAICompatibleClient(
            base_url=str(base_url),
            api_key=api_key,
            model=str(model),
            temperature=float(llm_config.get("temperature", 0.2)),
            max_tokens=int(llm_config.get("max_tokens", 512)),
            timeout=float(llm_config.get("timeout", 120)),
            stream=backend == "vllm",
            max_retries=int(llm_config.get("max_retries", 2)),
            backend=backend,
            enable_agent_meta=enable_agent_meta,
            agent_meta_builder=agent_meta_builder,
        )

    raise ValueError(f"不支持的 llm.backend: {backend}")


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _valid_http_url(value: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
