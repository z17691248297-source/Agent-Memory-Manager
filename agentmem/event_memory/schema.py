from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentmem.event_memory.memory_delta import ArtifactRef, DeltaDecision, Fact


@dataclass
class TaskStateView:
    goals: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    decisions: list[DeltaDecision] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    tool_summaries: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recent_context: list[str] = field(default_factory=list)
    final_answer: str = ""
    global_state: dict[str, Any] = field(default_factory=dict)
    stage_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_updated_round: int = 0

    @property
    def task_goal(self) -> str:
        return self.goals[0] if self.goals else ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskStateView":
        return cls(
            goals=list(data.get("goals") or ([] if not data.get("task_goal") else [str(data.get("task_goal"))])),
            constraints=list(data.get("constraints") or []),
            facts=[Fact(**item) for item in data.get("facts") or []],
            decisions=[DeltaDecision(**item) for item in data.get("decisions") or []],
            open_questions=list(data.get("open_questions") or []),
            todos=list(data.get("todos") or []),
            artifact_refs=[ArtifactRef(**item) for item in data.get("artifact_refs") or []],
            tool_summaries=list(data.get("tool_summaries") or []),
            warnings=list(data.get("warnings") or []),
            recent_context=list(data.get("recent_context") or []),
            final_answer=str(data.get("final_answer", "")),
            global_state=dict(data.get("global_state") or {}),
            stage_state=dict(data.get("stage_state") or {}),
            last_updated_round=int(data.get("last_updated_round", 0) or 0),
        )
