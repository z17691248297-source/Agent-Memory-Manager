from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any


class MemoryPlanLogger:
    """Append per-request memory planning records for vLLM agent_meta runs."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def record(
        self,
        *,
        run_id: str,
        stage: str,
        context_id: str,
        segment_type: str,
        priority: str | None,
        ttl: int | None,
        included_items: list[Any] | None = None,
        external_refs: list[Any] | None = None,
        excluded_items: list[Any] | None = None,
        estimated_prompt_tokens: int = 0,
        estimated_saved_tokens: int = 0,
        agent_meta: dict[str, Any] | None = None,
    ) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{_safe_name(run_id or 'agentmem_session')}.jsonl"
        payload = {
            "recorded_at": time.time(),
            "run_id": str(run_id),
            "agent_id": str((agent_meta or {}).get("agent_id") or os.getenv("AGENTMEM_AGENT_ID", "")),
            "stage": str(stage),
            "context_id": str(context_id),
            "segment_type": str(segment_type),
            "priority": "" if priority is None else str(priority),
            "ttl": -1 if ttl is None else int(ttl),
            "included_items": _jsonable_list(included_items or []),
            "external_refs": _jsonable_list(external_refs or []),
            "excluded_items": _jsonable_list(excluded_items or []),
            "estimated_prompt_tokens": int(estimated_prompt_tokens or 0),
            "estimated_saved_tokens": int(estimated_saved_tokens or 0),
            "agent_meta": _jsonable(agent_meta or {}),
        }
        with path.open("a", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, sort_keys=True)
            file.write("\n")
        return path


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return safe[:120] or "agentmem_session"


def _jsonable_list(values: list[Any]) -> list[Any]:
    return [_jsonable(value) for value in values]


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(key): _jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_jsonable(item) for item in value]
        return str(value)
