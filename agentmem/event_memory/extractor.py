from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from agentmem.event_memory.event import AgentEvent
from agentmem.event_memory.memory_delta import MemoryDelta
from agentmem.event_memory.memory_delta import MemoryDeltaParser
from agentmem.runtime.llm_client import OpenAICompatibleClient


@dataclass
class ExtractedFacts:
    """Compatibility wrapper for older imports.

    Event-sourced memory no longer extracts domain facts from natural language.
    Structured memory updates enter through explicit MemoryDelta events.
    """

    memory_delta: MemoryDelta


@dataclass(frozen=True)
class ExtractorConfig:
    enabled: bool = False
    backend: str = "vllm"
    base_url: str = "http://localhost:9000/v1"
    api_key: str = "EMPTY"
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout: float = 120.0
    max_retries: int = 0
    healthcheck_timeout: float = 3.0
    extra_body: dict[str, Any] | None = None


class StructuredExtractor:
    """Compatibility extractor used when the external extractor is disabled.

    The core memory layer must not encode benchmark-specific vocabulary or
    parse tool output into task facts. Tools produce artifact summaries, the
    agent writes durable state through memory_delta, and an optional external
    model can generate only that generic memory_delta schema.
    """

    def extract(self, event: AgentEvent) -> ExtractedFacts:
        return ExtractedFacts(memory_delta=MemoryDelta())


class ExternalMemoryDeltaExtractor:
    """Generate structured memory_delta with a secondary OpenAI-compatible model."""

    def __init__(self, config: ExtractorConfig) -> None:
        self.config = config
        self.client = OpenAICompatibleClient(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            stream=False,
            max_retries=config.max_retries,
            extra_body=config.extra_body,
        )
        self.parser = MemoryDeltaParser()
        self.last_error = ""
        self._available: bool | None = None

    def extract_memory_delta(self, payload: dict[str, Any]) -> MemoryDelta:
        self.last_error = ""
        if not self._is_available():
            return MemoryDelta()
        try:
            response = self.client.chat(
                [
                    {"role": "system", "content": _EXTRACTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            return self._parse_response(str(response.get("content", "")))
        except Exception as exc:  # noqa: BLE001 - extractor failure must not fail benchmark
            self.last_error = str(exc)
            self._available = False
            return MemoryDelta()

    def _parse_response(self, content: str) -> MemoryDelta:
        text = content.strip()
        if not text:
            return MemoryDelta()
        data = _load_json_object(text)
        if data is None:
            self.last_error = "extractor returned non-json output"
            return MemoryDelta()
        delta_payload = data.get("memory_delta", data)
        if not isinstance(delta_payload, dict):
            self.last_error = "extractor memory_delta is not an object"
            return MemoryDelta()
        return self.parser.parse({"assistant_response": "", "memory_delta": delta_payload}).memory_delta

    def _is_available(self) -> bool:
        if self._available is not None:
            return self._available
        models_url = urljoin(self.config.base_url.rstrip("/") + "/", "models")
        try:
            request = Request(models_url, headers={"Authorization": f"Bearer {self.config.api_key}"})
            with urlopen(request, timeout=self.config.healthcheck_timeout) as response:  # noqa: S310
                self._available = 200 <= int(response.status) < 500
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"extractor healthcheck failed: {exc}"
            self._available = False
        return bool(self._available)


def build_memory_delta_extractor(config: dict[str, Any] | None) -> ExternalMemoryDeltaExtractor | None:
    extractor_config = extractor_config_from_runtime(config)
    if not extractor_config.enabled:
        return None
    return ExternalMemoryDeltaExtractor(extractor_config)


def extractor_config_from_runtime(config: dict[str, Any] | None) -> ExtractorConfig:
    import os

    raw = dict((config or {}).get("extractor") or {})
    enabled = _bool(os.getenv("AGENTMEM_EXTRACTOR_ENABLED", raw.get("enabled", False)))
    backend = str(os.getenv("AGENTMEM_EXTRACTOR_BACKEND", raw.get("backend", "vllm"))).replace("-", "_").lower()
    base_url = str(os.getenv("AGENTMEM_EXTRACTOR_BASE_URL", raw.get("base_url", "http://localhost:9000/v1")))
    api_key = str(os.getenv("AGENTMEM_EXTRACTOR_API_KEY", raw.get("api_key", "EMPTY")))
    model = str(os.getenv("AGENTMEM_EXTRACTOR_MODEL", raw.get("model", "")))
    return ExtractorConfig(
        enabled=enabled,
        backend=backend,
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=float(raw.get("temperature", 0)),
        max_tokens=int(raw.get("max_tokens", 1024)),
        timeout=float(raw.get("timeout", 120)),
        max_retries=int(raw.get("max_retries", 0)),
        healthcheck_timeout=float(raw.get("healthcheck_timeout", 3)),
        extra_body=_extractor_extra_body(raw, backend),
    )


_EXTRACTOR_SYSTEM_PROMPT = """You generate only structured JSON for Event-Sourced Memory.
Return a JSON object with one key: memory_delta.
memory_delta must use exactly these keys:
goals, constraints, facts, decisions, open_questions, todos, artifact_refs, tool_summaries, warnings.
Do not answer the user. Do not include markdown. Do not invent facts not supported by the provided context.
facts items use content, source, confidence, importance, evidence_ref.
decisions items use content, reason, confidence, source.
artifact_refs items use result_id, tool_name, artifact_type, path, summary, token_count."""
_EXTRACTOR_SYSTEM_PROMPT += """
For Qwen thinking models, do not output a thinking process. Output the final JSON object only.
If required_facts are provided, inspect tool_summaries, tool_key_findings, artifact_refs, recent_context, and assistant_response.
If assistant_response conflicts with tool_summaries, tool_key_findings, or artifact_refs, trust the tool evidence.
For every required_fact supported by those inputs, add a fact with evidence_ref.
For missing required facts, add warnings entries formatted as missing_required_fact:<fact>.
Add decisions describing what the final answer must cover."""


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _load_json_object(text: str) -> dict[str, Any] | None:
    stripped = _strip_code_fence(text)
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    fallback: dict[str, Any] | None = None
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            data, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if "memory_delta" in data:
            return data
        if fallback is None and any(key in data for key in _MEMORY_DELTA_KEYS):
            fallback = data
    return fallback


def _extractor_extra_body(raw: dict[str, Any], backend: str) -> dict[str, Any] | None:
    extra_body = raw.get("extra_body")
    if isinstance(extra_body, dict):
        return dict(extra_body)
    if backend == "vllm" and _bool(raw.get("disable_thinking", True)):
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


_MEMORY_DELTA_KEYS = {
    "goals",
    "constraints",
    "facts",
    "decisions",
    "open_questions",
    "todos",
    "artifact_refs",
    "tool_summaries",
    "warnings",
}
