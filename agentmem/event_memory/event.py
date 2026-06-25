from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from agentmem.memory.memory_object import estimate_tokens


EVENT_TYPES = {
    "user_message",
    "agent_plan",
    "tool_call",
    "tool_result",
    "observation",
    "agent_observation",
    "metric",
    "decision",
    "reflection",
    "branch_start",
    "branch_result",
    "branch_commit",
    "branch_rollback",
    "memory_snapshot",
    "memory_delta",
    "final_answer",
    "evaluation_result",
}


@dataclass
class AgentEvent:
    event_id: str
    run_id: str
    session_id: str
    round: int
    stage: str
    event_type: str
    content: str | None = None
    content_path: str | None = None
    token_count: int = 0
    source: str = "agent"
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported event_type: {self.event_type}")
        if self.token_count <= 0 and self.content:
            self.token_count = estimate_tokens(self.content)
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentEvent":
        return cls(
            event_id=str(data["event_id"]),
            run_id=str(data["run_id"]),
            session_id=str(data.get("session_id", data.get("run_id", ""))),
            round=int(data.get("round", 0)),
            stage=str(data.get("stage", "")),
            event_type=str(data["event_type"]),
            content=data.get("content"),
            content_path=data.get("content_path"),
            token_count=int(data.get("token_count", 0) or 0),
            source=str(data.get("source", "agent")),
            timestamp=float(data.get("timestamp", time.time())),
            metadata=dict(data.get("metadata") or {}),
        )
