from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from agentmem.event_memory.event import AgentEvent
from agentmem.event_memory.memory_delta import ArtifactRef, MemoryDelta
from agentmem.event_memory.reducer import StateReducer
from agentmem.event_memory.schema import TaskStateView


class MemoryProjector:
    """Project generic AgentEvents into a compact TaskStateView."""

    def __init__(self, reducer: StateReducer | None = None) -> None:
        self.reducer = reducer or StateReducer()

    def apply_event(self, state: TaskStateView, event: AgentEvent) -> TaskStateView:
        next_state = deepcopy(state)
        if event.event_type == "user_message":
            next_state.recent_context.append(_recent_line("user", event.content))
        elif event.event_type == "tool_result":
            artifact = _artifact_from_event(event)
            if artifact:
                next_state.artifact_refs.append(artifact)
            if event.content:
                next_state.tool_summaries.append(_compact(event.content))
            next_state.recent_context.append(_recent_line(f"tool:{event.source}", event.content))
        elif event.event_type == "memory_delta":
            _apply_delta(next_state, MemoryDelta.from_dict(event.metadata.get("memory_delta") or {}))
        elif event.event_type == "final_answer":
            next_state.final_answer = _compact(event.content or "", max_chars=1200)
            next_state.recent_context.append(_recent_line("assistant", event.content))
        elif event.event_type in {"reflection", "agent_plan", "decision", "observation"}:
            next_state.recent_context.append(_recent_line(event.source or "assistant", event.content))

        next_state.last_updated_round = max(next_state.last_updated_round, int(event.round or 0))
        next_state = self.reducer.reduce(next_state)
        next_state.global_state = _global_state(next_state)
        next_state.stage_state[event.stage or "unknown"] = _stage_state(next_state, event.stage or "unknown")
        return next_state

    def replay(self, events: Iterable[AgentEvent], initial_state: TaskStateView | None = None) -> TaskStateView:
        state = deepcopy(initial_state) if initial_state else TaskStateView()
        for event in events:
            state = self.apply_event(state, event)
        return state


def _apply_delta(state: TaskStateView, delta: MemoryDelta) -> None:
    state.goals.extend(delta.goals)
    state.constraints.extend(delta.constraints)
    state.facts.extend(delta.facts)
    state.decisions.extend(delta.decisions)
    state.open_questions.extend(delta.open_questions)
    state.todos.extend(delta.todos)
    state.artifact_refs.extend(delta.artifact_refs)
    state.tool_summaries.extend(delta.tool_summaries)
    state.warnings.extend(delta.warnings)


def _artifact_from_event(event: AgentEvent) -> ArtifactRef | None:
    metadata = dict(event.metadata or {})
    artifacts = metadata.get("artifacts")
    if isinstance(artifacts, list) and artifacts:
        first = next((item for item in artifacts if isinstance(item, dict)), None)
        if first:
            return ArtifactRef(
                result_id=str(metadata.get("result_id") or first.get("result_id") or ""),
                tool_name=str(metadata.get("tool_name") or first.get("tool_name") or event.source or ""),
                artifact_type=str(first.get("artifact_type") or "text"),
                path=str(first.get("path") or event.content_path or ""),
                summary=str(first.get("description") or metadata.get("summary") or event.content or ""),
                token_count=int(first.get("token_count") or metadata.get("raw_token_len") or 0),
            )
    result_id = str(metadata.get("result_id") or "")
    path = str(metadata.get("path") or event.content_path or "")
    if not result_id and not path:
        return None
    return ArtifactRef(
        result_id=result_id,
        tool_name=str(metadata.get("tool_name") or event.source or ""),
        artifact_type=str(metadata.get("artifact_type") or "text"),
        path=path,
        summary=str(metadata.get("summary") or event.content or ""),
        token_count=int(metadata.get("raw_token_len") or metadata.get("summary_token_len") or 0),
    )


def _global_state(state: TaskStateView) -> dict:
    return {
        "goal_count": len(state.goals),
        "constraint_count": len(state.constraints),
        "fact_count": len(state.facts),
        "decision_count": len(state.decisions),
        "artifact_ref_count": len(state.artifact_refs),
        "last_updated_round": state.last_updated_round,
    }


def _stage_state(state: TaskStateView, stage: str) -> dict:
    return {
        "stage": stage,
        "goals": state.goals[:3],
        "facts": [item.content for item in state.facts[:8]],
        "decisions": [item.content for item in state.decisions[:5]],
        "artifact_refs": [item.result_id for item in state.artifact_refs[:8]],
    }


def _recent_line(role: str, content: str | None) -> str:
    return f"{role}: {_compact(content or '')}"


def _compact(text: str, max_chars: int = 500) -> str:
    single = " ".join(str(text).split())
    if len(single) <= max_chars:
        return single
    return single[:max_chars]
