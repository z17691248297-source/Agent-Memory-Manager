from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class CacheStatsCollector:
    """Best-effort reader for the vLLM AgentMem cache stats endpoint."""

    def __init__(self, metrics_url: str, timeout: int = 10):
        self.metrics_url = str(metrics_url)
        self.timeout = int(timeout)

    def fetch(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(self.metrics_url, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            return {
                "available": False,
                "unavailable_reason": str(exc),
                "metrics_url": self.metrics_url,
            }
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {
                "available": False,
                "unavailable_reason": f"invalid_json: {exc}",
                "metrics_url": self.metrics_url,
                "raw": raw[:1000],
            }
        if not isinstance(data, dict):
            return {
                "available": False,
                "unavailable_reason": "response_json_is_not_object",
                "metrics_url": self.metrics_url,
                "raw": data,
            }
        flattened = self.flatten(data)
        return {
            "available": True,
            "unavailable_reason": "",
            "metrics_url": self.metrics_url,
            "raw": data,
            **flattened,
        }

    def flatten(self, stats: dict[str, Any]) -> dict[str, Any]:
        output = {
            "cache_total_blocks": _find_number(stats, ["total_blocks", "cache_total_blocks", "num_total_blocks", "num_agent_blocks"]),
            "cache_agent_sessions": _find_number(stats, ["agent_sessions", "sessions", "session_count", "num_sessions"]),
            "cache_tool_result_blocks": _segment_blocks(stats, "tool_result"),
            "cache_shared_prefix_blocks": _segment_blocks(stats, "shared_prefix"),
            "cache_scratchpad_blocks": _segment_blocks(stats, "scratchpad"),
            "cache_expired_branch_blocks": _segment_blocks(stats, "expired_branch"),
        }
        return {key: (-1 if value is None else value) for key, value in output.items()}


def _find_number(value: Any, names: list[str]) -> int | float | None:
    if isinstance(value, dict):
        for name in names:
            if name in value and isinstance(value[name], (int, float)):
                return value[name]
            if name in value and isinstance(value[name], dict):
                return len(value[name])
        for item in value.values():
            found = _find_number(item, names)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_number(item, names)
            if found is not None:
                return found
    return None


def _segment_blocks(stats: dict[str, Any], segment_type: str) -> int | float | None:
    for container_key in ["segments", "segment_type", "segment_types", "by_segment_type", "blocks_by_segment_type"]:
        container = stats.get(container_key)
        found = _segment_blocks_from_container(container, segment_type)
        if found is not None:
            return found
    return _find_segment_recursive(stats, segment_type)


def _segment_blocks_from_container(container: Any, segment_type: str) -> int | float | None:
    if isinstance(container, dict):
        item = container.get(segment_type)
        if isinstance(item, (int, float)):
            return item
        if isinstance(item, dict):
            return _first_numeric_key(item, ["blocks", "block_count", "num_blocks", "count", "cached_blocks"])
    if isinstance(container, list):
        for item in container:
            if not isinstance(item, dict):
                continue
            if str(item.get("segment_type") or item.get("name") or item.get("segment")) == segment_type:
                return _first_numeric_key(item, ["blocks", "block_count", "num_blocks", "count", "cached_blocks"])
    return None


def _find_segment_recursive(value: Any, segment_type: str) -> int | float | None:
    if isinstance(value, dict):
        if str(value.get("segment_type") or value.get("name") or value.get("segment")) == segment_type:
            found = _first_numeric_key(value, ["blocks", "block_count", "num_blocks", "count", "cached_blocks"])
            if found is not None:
                return found
        for item in value.values():
            found = _find_segment_recursive(item, segment_type)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_segment_recursive(item, segment_type)
            if found is not None:
                return found
    return None


def _first_numeric_key(value: dict[str, Any], names: list[str]) -> int | float | None:
    for name in names:
        if isinstance(value.get(name), (int, float)):
            return value[name]
    return None
