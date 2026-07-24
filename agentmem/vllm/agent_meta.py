from __future__ import annotations

import os
from typing import Any


SEGMENT_PRIORITY_DEFAULTS: dict[str, str] = {
    "system": "high",
    "tool_schema": "high",
    "shared_prefix": "high",
    "user_message": "normal",
    "assistant_message": "normal",
    "tool_result": "normal",
    "mcp_result": "normal",
    "scratchpad": "low",
    "expired_branch": "drop",
}


STAGE_SEGMENT_DEFAULTS: dict[str, str] = {
    "planning": "scratchpad",
    "tool_calling": "tool_result",
    "reflection": "scratchpad",
    "final_answer": "assistant_message",
    "branching": "shared_prefix",
    "prefix_cache": "shared_prefix",
    "ablation": "shared_prefix",
    "refill": "assistant_message",
}


def default_segment_type_for_stage(stage: str) -> str:
    """Map AgentMem runtime stages onto vLLM agent-aware cache segments."""
    return STAGE_SEGMENT_DEFAULTS.get(str(stage or "").lower(), "user_message")


class AgentMetaBuilder:
    """Build JSON-serializable agent_meta payloads for vLLM extra_body."""

    def __init__(self, agent_id: str, default_ttl: int = 300):
        self.agent_id = str(agent_id or "agentmem")
        self.default_ttl = int(default_ttl)

    def build(
        self,
        run_id: str,
        stage: str,
        segment_type: str,
        context_id: str | None = None,
        source: str = "agentmem",
        tool_name: str | None = None,
        priority: str | None = None,
        ttl: int | None = None,
        branch_id: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
        cache_namespace: str | None = None,
    ) -> dict[str, Any]:
        run_id = str(run_id)
        stage = str(stage)
        segment_type = str(segment_type or default_segment_type_for_stage(stage))
        resolved_experiment_id = str(experiment_id or os.getenv("AGENTMEM_EXPERIMENT_ID", ""))
        resolved_session_id = str(session_id or run_id)
        ttl_seconds = int(self.default_ttl if ttl is None else ttl)
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "session_id": resolved_session_id,
            "experiment_id": resolved_experiment_id,
            "run_id": run_id,
            "context_id": str(context_id or f"{run_id}:{stage}:{segment_type}"),
            "segment_type": segment_type,
            "source": str(source),
            "priority": str(priority or SEGMENT_PRIORITY_DEFAULTS.get(segment_type, "normal")),
            "ttl_seconds": ttl_seconds,
            "ttl": ttl_seconds,
            "branch_id": str(branch_id or ""),
            "cache_namespace": str(cache_namespace or f"{resolved_experiment_id}:{self.agent_id}:{resolved_session_id}"),
        }
        if tool_name:
            payload["tool_name"] = str(tool_name)
        return payload
