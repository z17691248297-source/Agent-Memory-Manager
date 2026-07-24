from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when AgentMem configuration is incomplete or unsafe."""


ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")
SAFE_EMPTY_API_KEYS = {"", "EMPTY", "<API_KEY>", "<optional>", "null", "None"}
MOCK_BACKENDS = {"mock", "fake", "local", "local_deterministic"}


def load_config(
    path: str | Path | None,
    *,
    validate: bool = False,
    release: bool | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Load YAML/JSON config and expand ${ENV_NAME} placeholders.

    Validation is opt-in so read-only commands can display example configs
    without requiring users to export every value. Runtime client construction
    and reproduce scripts enable validation.
    """

    config_path = Path(path) if path else Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    if not config_path.exists():
        raise ConfigError(f"configuration file not found: {config_path}")
    raw = config_path.read_text(encoding="utf-8")
    data = _parse_mapping(raw)
    resolved = _expand_env(data, environ or os.environ)
    _apply_legacy_env_overrides(resolved, environ or os.environ)
    if release is None:
        release = bool(dict(resolved.get("benchmark") or {}).get("release", False))
    if validate:
        validate_config(resolved, release=bool(release))
    return resolved


def validate_config(config: dict[str, Any], *, release: bool = False) -> None:
    llm = dict(config.get("llm") or {})
    extractor = dict(config.get("extractor") or {})
    agent = dict(config.get("agent") or {})
    vllm = dict(config.get("vllm") or {})
    benchmark = dict(config.get("benchmark") or {})
    isolation = dict(config.get("cache_isolation") or {})

    backend = str(llm.get("backend") or "").replace("-", "_").lower()
    if not backend:
        raise ConfigError("llm.backend is required")
    if release and backend in MOCK_BACKENDS:
        raise ConfigError("release configuration must not use a mock/local backend")

    _require_positive_int(benchmark, "repeat", "benchmark.repeat")
    _require_positive_int(agent, "max_steps", "agent.max_steps")
    _require_positive_number(llm, "timeout", "llm.timeout")
    _require_non_negative_int(benchmark, "warmup", "benchmark.warmup", required=False)

    if not str(llm.get("model") or "").strip():
        raise ConfigError("llm.model is required")
    if backend in {"vllm", "openai", "openai_compatible"}:
        _require_url(llm.get("base_url"), "llm.base_url")

    if _as_bool(extractor.get("enabled")):
        _require_url(extractor.get("base_url"), "extractor.base_url")
        _require_positive_number(extractor, "timeout", "extractor.timeout")
        if not str(extractor.get("model") or "").strip():
            raise ConfigError("extractor.model is required when extractor.enabled=true")

    if backend == "vllm":
        if vllm.get("metrics_url"):
            _require_url(vllm.get("metrics_url"), "vllm.metrics_url")
        if vllm.get("cache_stats_url"):
            _require_url(vllm.get("cache_stats_url"), "vllm.cache_stats_url")
        if vllm.get("metrics_url") and not vllm.get("cache_stats_url"):
            # /metrics is allowed alone, but explicit warning would be hidden in CLI.
            pass
        if _as_bool(vllm.get("enable_agent_meta")) and not str(vllm.get("agent_id") or "").strip():
            raise ConfigError("vllm.agent_id is required when vllm.enable_agent_meta=true")

    strategy = str(isolation.get("strategy") or "snapshot_delta")
    allowed_strategies = {"restart", "reset_endpoint", "namespace_isolation", "snapshot_delta"}
    if strategy not in allowed_strategies:
        raise ConfigError(f"cache_isolation.strategy must be one of {sorted(allowed_strategies)}")
    if strategy == "reset_endpoint" and not vllm.get("cache_reset_url"):
        raise ConfigError("vllm.cache_reset_url is required when cache_isolation.strategy=reset_endpoint")


def resolved_config_hash(config: dict[str, Any]) -> str:
    sanitized = deepcopy(config)
    for section_name in ["llm", "extractor"]:
        section = sanitized.get(section_name)
        if isinstance(section, dict) and "api_key" in section:
            section["api_key"] = "<redacted>"
    payload = json.dumps(sanitized, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_resolved_config(path: str | Path, config: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore

        text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    except Exception:
        text = json.dumps(config, ensure_ascii=False, indent=2)
    output.write_text(text, encoding="utf-8")
    return output


def resolve_api_key(section: dict[str, Any], *, environ: dict[str, str] | None = None) -> str:
    env = environ or os.environ
    env_name = str(section.get("api_key_env") or "").strip()
    if env_name and env.get(env_name) is not None:
        return str(env.get(env_name) or "")
    value = str(section.get("api_key") or "")
    return "" if value in SAFE_EMPTY_API_KEYS else value


def _parse_mapping(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return dict(data)
        raise ConfigError("configuration root must be a mapping")
    except ImportError:
        pass
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    pending_key: str | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            value = _parse_env_scalar(line[2:].strip())
            if not isinstance(parent, list):
                if not isinstance(stack[-2][1], dict) or pending_key is None:
                    raise ConfigError("invalid YAML list placement")
                new_list: list[Any] = []
                stack[-2][1][pending_key] = new_list
                stack[-1] = (stack[-1][0], new_list)
                parent = new_list
            parent.append(value)
            continue
        if ":" not in line or not isinstance(parent, dict):
            raise ConfigError(f"unsupported YAML line: {raw}")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value == "":
            value: Any = {}
            parent[key] = value
            stack.append((indent, value))
            pending_key = key
        else:
            parent[key] = _parse_env_scalar(raw_value)
            pending_key = key
    return root


def _expand_env(value: Any, environ: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item, environ) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item, environ) for item in value]
    if not isinstance(value, str):
        return value
    matches = list(ENV_PATTERN.finditer(value))
    if not matches:
        return value
    expanded = value
    for match in matches:
        name, default = match.group(1), match.group(2)
        replacement = environ.get(name, default if default is not None else "")
        expanded = expanded.replace(match.group(0), replacement)
    return _parse_env_scalar(expanded)


def _parse_env_scalar(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"[-+]?\d+", value.strip()):
        try:
            return int(value)
        except ValueError:
            return value
    if re.fullmatch(r"[-+]?\d+\.\d+", value.strip()):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _apply_legacy_env_overrides(config: dict[str, Any], environ: dict[str, str]) -> None:
    llm = config.setdefault("llm", {})
    if isinstance(llm, dict):
        if environ.get("AGENTMEM_LLM_BACKEND"):
            llm["backend"] = environ["AGENTMEM_LLM_BACKEND"]
        if environ.get("AGENTMEM_LLM_BASE_URL"):
            llm["base_url"] = environ["AGENTMEM_LLM_BASE_URL"]
        if environ.get("AGENTMEM_MODEL"):
            llm["model"] = environ["AGENTMEM_MODEL"]
    vllm = config.setdefault("vllm", {})
    if isinstance(vllm, dict):
        if environ.get("AGENTMEM_VLLM_METRICS_URL"):
            vllm["metrics_url"] = environ["AGENTMEM_VLLM_METRICS_URL"]
        if environ.get("AGENTMEM_CACHE_STATS_URL"):
            vllm["cache_stats_url"] = environ["AGENTMEM_CACHE_STATS_URL"]
        if environ.get("AGENTMEM_ENABLE_AGENT_META"):
            vllm["enable_agent_meta"] = _as_bool(environ["AGENTMEM_ENABLE_AGENT_META"])
        if environ.get("AGENTMEM_AGENT_ID"):
            vllm["agent_id"] = environ["AGENTMEM_AGENT_ID"]
    extractor = config.setdefault("extractor", {})
    if isinstance(extractor, dict):
        if environ.get("AGENTMEM_EXTRACTOR_ENABLED"):
            extractor["enabled"] = _as_bool(environ["AGENTMEM_EXTRACTOR_ENABLED"])
        if environ.get("AGENTMEM_EXTRACTOR_BASE_URL"):
            extractor["base_url"] = environ["AGENTMEM_EXTRACTOR_BASE_URL"]
        if environ.get("AGENTMEM_EXTRACTOR_MODEL"):
            extractor["model"] = environ["AGENTMEM_EXTRACTOR_MODEL"]
    benchmark = config.setdefault("benchmark", {})
    if isinstance(benchmark, dict):
        if environ.get("AGENTMEM_OUTPUT_DIR"):
            benchmark["output_dir"] = environ["AGENTMEM_OUTPUT_DIR"]
        if environ.get("AGENTMEM_SEED"):
            benchmark["seed"] = _parse_env_scalar(environ["AGENTMEM_SEED"])


def _require_positive_int(section: dict[str, Any], key: str, label: str) -> None:
    value = section.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{label} must be an integer > 0") from None
    if parsed <= 0:
        raise ConfigError(f"{label} must be > 0")


def _require_non_negative_int(section: dict[str, Any], key: str, label: str, *, required: bool = True) -> None:
    value = section.get(key)
    if value is None and not required:
        return
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{label} must be an integer >= 0") from None
    if parsed < 0:
        raise ConfigError(f"{label} must be >= 0")


def _require_positive_number(section: dict[str, Any], key: str, label: str) -> None:
    value = section.get(key)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{label} must be a number > 0") from None
    if parsed <= 0:
        raise ConfigError(f"{label} must be > 0")


def _require_url(value: Any, label: str) -> None:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{label} must be a valid http(s) URL")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
