from __future__ import annotations

from typing import Any


def build_cache_stats_payload(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(raw or {})
    payload.setdefault("scope", "global")
    payload.setdefault("unavailable", [])
    return payload
