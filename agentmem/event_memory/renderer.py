from __future__ import annotations

from agentmem.event_memory.schema import TaskStateView
from agentmem.memory.memory_object import estimate_tokens


class MemoryViewRenderer:
    """Render generic TaskStateView into a stable prompt segment."""

    def __init__(self, max_state_tokens: int = 900) -> None:
        self.max_state_tokens = max_state_tokens
        self.last_state_view_tokens = 0

    def render(self, state: TaskStateView, recent_turns: list[str], current_query: str, stage: str = "planning") -> str:
        facts = sorted(state.facts, key=lambda item: (item.importance, item.confidence), reverse=True)
        decisions = sorted(state.decisions, key=lambda item: item.confidence, reverse=True)
        artifact_refs = list(state.artifact_refs)
        recent_limit = 4 if stage == "final_answer" else 8
        parts = [
            "[Task State]",
            "Goals:",
            _bullet_lines(state.goals[:8]),
            "",
            "Constraints:",
            _bullet_lines(state.constraints[:10]),
            "",
            "Facts:",
            _bullet_lines([_fact_line(item) for item in facts[:14]]),
            "",
            "Decisions:",
            _bullet_lines([_decision_line(item) for item in decisions[:10]]),
            "",
            "Open Questions:",
            _bullet_lines(state.open_questions[:8]),
            "",
            "Todos:",
            _bullet_lines(state.todos[:10]),
            "",
            "Artifact References:",
            _bullet_lines([_artifact_line(item) for item in artifact_refs[:10]]),
            "",
            "Recent Context:",
            _bullet_lines(recent_turns[-recent_limit:]),
            "",
            "Current Query:",
            current_query or "",
        ]
        rendered = "\n".join(parts)
        rendered = self._fit_token_budget(rendered, state, recent_turns, current_query, stage)
        self.last_state_view_tokens = estimate_tokens(rendered)
        return f"state_view_tokens: {self.last_state_view_tokens}\n{rendered}"

    def _fit_token_budget(self, rendered: str, state: TaskStateView, recent_turns: list[str], current_query: str, stage: str) -> str:
        if estimate_tokens(rendered) <= self.max_state_tokens:
            return rendered
        facts = sorted(state.facts, key=lambda item: (item.importance, item.confidence), reverse=True)[:8]
        decisions = sorted(state.decisions, key=lambda item: item.confidence, reverse=True)[:6]
        recent_limit = 3 if stage == "final_answer" else 4
        parts = [
            "[Task State]",
            "Goals:",
            _bullet_lines([_shorten(item, 180) for item in state.goals[:5]]),
            "",
            "Constraints:",
            _bullet_lines([_shorten(item, 160) for item in state.constraints[:6]]),
            "",
            "Facts:",
            _bullet_lines([_shorten(_fact_line(item), 180) for item in facts]),
            "",
            "Decisions:",
            _bullet_lines([_shorten(_decision_line(item), 180) for item in decisions]),
            "",
            "Open Questions:",
            _bullet_lines([_shorten(item, 150) for item in state.open_questions[:5]]),
            "",
            "Todos:",
            _bullet_lines([_shorten(item, 140) for item in state.todos[:6]]),
            "",
            "Artifact References:",
            _bullet_lines([_shorten(_artifact_line(item), 180) for item in state.artifact_refs[:6]]),
            "",
            "Recent Context:",
            _bullet_lines([_shorten(line, 160) for line in recent_turns[-recent_limit:]]),
            "",
            "Current Query:",
            _shorten(current_query or "", 240),
        ]
        return "\n".join(parts)


def _bullet_lines(values: list[str]) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned:
        return "- none"
    return "\n".join(f"- {value}" for value in cleaned)


def _fact_line(fact) -> str:
    evidence = f"; evidence_ref={fact.evidence_ref}" if fact.evidence_ref else ""
    return f"{fact.content} (source={fact.source}, confidence={fact.confidence:.2f}, importance={fact.importance:.2f}{evidence})"


def _decision_line(decision) -> str:
    reason = f"; reason={decision.reason}" if decision.reason else ""
    return f"{decision.content} (source={decision.source}, confidence={decision.confidence:.2f}{reason})"


def _artifact_line(ref, max_summary_chars: int = 180) -> str:
    summary = _shorten(ref.summary, max_summary_chars)
    return (
        f"result_id={ref.result_id}; tool_name={ref.tool_name}; type={ref.artifact_type}; "
        f"path={ref.path}; token_count={ref.token_count}; summary={summary}"
    )


def _shorten(text: str, max_chars: int) -> str:
    single = " ".join(str(text).split())
    if len(single) <= max_chars:
        return single
    return single[:max_chars]
