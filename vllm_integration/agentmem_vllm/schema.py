from __future__ import annotations

from dataclasses import dataclass

SEGMENT_TYPES = {"system", "tool_schema", "shared_prefix", "user_message", "assistant_message", "tool_result", "mcp_result", "scratchpad", "expired_branch"}
PRIORITIES = {"high", "normal", "low", "drop"}


@dataclass(frozen=True)
class AgentMeta:
    agent_id: str
    session_id: str
    experiment_id: str = ""
    run_id: str = ""
    segment_type: str = "user_message"
    priority: str = "normal"
    ttl_seconds: int = 300
    branch_id: str = ""
    cache_namespace: str = ""

    def validate(self) -> None:
        for name in ["agent_id", "session_id", "experiment_id", "run_id", "branch_id", "cache_namespace"]:
            value = getattr(self, name)
            if len(value) > 256:
                raise ValueError(f"agent_meta.{name} too long")
        if self.segment_type not in SEGMENT_TYPES:
            raise ValueError(f"unsupported segment_type: {self.segment_type}")
        if self.priority not in PRIORITIES:
            raise ValueError(f"unsupported priority: {self.priority}")
        if self.ttl_seconds < 0 or self.ttl_seconds > 30 * 24 * 3600:
            raise ValueError("ttl_seconds out of range")
