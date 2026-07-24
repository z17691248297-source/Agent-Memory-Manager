from __future__ import annotations

from typing import Any

from .schema import AgentMeta


def parse_agent_meta(extra_body: dict[str, Any] | None) -> AgentMeta | None:
    payload = dict((extra_body or {}).get("agent_meta") or {})
    if not payload:
        return None
    ttl = payload.get("ttl_seconds", payload.get("ttl", 300))
    meta = AgentMeta(
        agent_id=str(payload.get("agent_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        experiment_id=str(payload.get("experiment_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        segment_type=str(payload.get("segment_type") or "user_message"),
        priority=str(payload.get("priority") or "normal"),
        ttl_seconds=int(ttl or 0),
        branch_id=str(payload.get("branch_id") or ""),
        cache_namespace=str(payload.get("cache_namespace") or ""),
    )
    meta.validate()
    return meta
