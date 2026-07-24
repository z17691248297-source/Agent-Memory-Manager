from __future__ import annotations

from dataclasses import dataclass

from agentmem.event_memory.memory_delta import ArtifactRef, DeltaDecision, Fact
from agentmem.event_memory.schema import TaskStateView


@dataclass
class StateReducer:
    max_goals: int = 8
    max_constraints: int = 20
    max_facts: int = 40
    max_decisions: int = 20
    max_artifact_refs: int = 30
    max_open_questions: int = 12
    max_todos: int = 20
    max_tool_summaries: int = 20
    max_warnings: int = 12
    max_recent_context: int = 12

    def reduce(self, state: TaskStateView) -> TaskStateView:
        state.goals = _dedupe_strings(state.goals)[: self.max_goals]
        state.constraints = _dedupe_strings(state.constraints)[: self.max_constraints]
        state.facts = self._reduce_facts(state.facts)
        state.decisions = self._reduce_decisions(state.decisions)
        state.artifact_refs = self._reduce_artifact_refs(state.artifact_refs)
        state.open_questions = _dedupe_strings(state.open_questions)[: self.max_open_questions]
        state.todos = _dedupe_strings(state.todos)[: self.max_todos]
        state.tool_summaries = _dedupe_strings(state.tool_summaries)[: self.max_tool_summaries]
        state.warnings = _dedupe_strings(state.warnings)[: self.max_warnings]
        state.recent_context = [item for item in state.recent_context if str(item).strip()][-self.max_recent_context :]
        return state

    def _reduce_facts(self, facts: list[Fact]) -> list[Fact]:
        protected: list[tuple[int, Fact]] = []
        merged: dict[tuple[str, str], tuple[int, Fact]] = {}
        by_type: dict[str, Fact] = {}
        for index, fact in enumerate(facts):
            candidate = _copy_fact(fact)
            candidate.confidence = _bounded(candidate.confidence)
            candidate.importance = _bounded(candidate.importance)
            if candidate.protected:
                protected.append((index, candidate))
                by_type.setdefault(_norm(candidate.fact_type), candidate)
                continue
            conflict_base = by_type.get(_norm(candidate.fact_type))
            if conflict_base and _norm(conflict_base.content) != _norm(candidate.content):
                candidate.conflict = True
                candidate.version = max(candidate.version, conflict_base.version + 1)
                candidate.supersedes = candidate.supersedes or conflict_base.fact_id
            key = (_norm(candidate.source), _norm(candidate.content))
            if key not in merged or _rank(candidate, index) >= _rank(merged[key][1], merged[key][0]):
                merged[key] = (index, candidate)
            by_type.setdefault(_norm(candidate.fact_type), candidate)
        ordered = sorted([*protected, *merged.values()], key=lambda item: _rank(item[1], item[0]), reverse=True)
        deduped: list[Fact] = []
        seen: set[tuple[str, str, str]] = set()
        for _, fact in ordered:
            key = (_norm(fact.fact_id), _norm(fact.source), _norm(fact.content))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(fact)
        return deduped[: self.max_facts]

    def _reduce_decisions(self, decisions: list[DeltaDecision]) -> list[DeltaDecision]:
        merged: dict[str, tuple[int, DeltaDecision]] = {}
        for index, decision in enumerate(decisions):
            key = _norm(decision.content)
            if not key:
                continue
            candidate = DeltaDecision(
                content=decision.content,
                reason=decision.reason,
                confidence=_bounded(decision.confidence),
                source=decision.source,
            )
            if key not in merged or (candidate.confidence, index) >= (merged[key][1].confidence, merged[key][0]):
                merged[key] = (index, candidate)
        ordered = sorted(merged.values(), key=lambda item: (item[1].confidence, item[0]), reverse=True)
        return [item for _, item in ordered[: self.max_decisions]]

    def _reduce_artifact_refs(self, refs: list[ArtifactRef]) -> list[ArtifactRef]:
        merged: dict[str, tuple[int, ArtifactRef]] = {}
        for index, ref in enumerate(refs):
            key = ref.result_id or ref.path
            if not key:
                continue
            candidate = ArtifactRef(
                result_id=ref.result_id,
                tool_name=ref.tool_name,
                artifact_type=ref.artifact_type or "text",
                path=ref.path,
                summary=ref.summary,
                token_count=int(ref.token_count or 0),
            )
            if key not in merged or index >= merged[key][0]:
                merged[key] = (index, candidate)
        ordered = sorted(merged.values(), key=lambda item: item[0], reverse=True)
        return [item for _, item in ordered[: self.max_artifact_refs]]


def _copy_fact(fact: Fact) -> Fact:
    return Fact(
        content=fact.content,
        source=fact.source,
        confidence=fact.confidence,
        importance=fact.importance,
        evidence_ref=fact.evidence_ref,
        fact_id=fact.fact_id,
        fact_type=fact.fact_type,
        source_event_id=fact.source_event_id,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        access_count=fact.access_count,
        last_accessed_at=fact.last_accessed_at,
        expires_at=fact.expires_at,
        protected=fact.protected,
        version=fact.version,
        conflict=fact.conflict,
        supersedes=fact.supersedes,
    )


def _rank(fact: Fact, index: int) -> tuple[float, float, int]:
    return (_bounded(fact.importance), _bounded(fact.confidence), index)


def _bounded(value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    return max(0.0, min(1.0, parsed))


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = " ".join(str(value).split())
        if not text:
            continue
        key = _norm(text)
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _norm(value: str) -> str:
    return " ".join(str(value).lower().split())
