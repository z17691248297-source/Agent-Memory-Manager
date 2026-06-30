from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Fact:
    content: str
    source: str = "assistant"
    confidence: float = 0.75
    importance: float = 0.5
    evidence_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeltaDecision:
    content: str
    reason: str = ""
    confidence: float = 0.75
    source: str = "assistant"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArtifactRef:
    result_id: str
    tool_name: str = ""
    artifact_type: str = "text"
    path: str = ""
    summary: str = ""
    token_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryDelta:
    goals: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    decisions: list[DeltaDecision] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    tool_summaries: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            [
                self.goals,
                self.constraints,
                self.facts,
                self.decisions,
                self.open_questions,
                self.todos,
                self.artifact_refs,
                self.tool_summaries,
                self.warnings,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "goals": list(self.goals),
            "constraints": list(self.constraints),
            "facts": [item.to_dict() for item in self.facts],
            "decisions": [item.to_dict() for item in self.decisions],
            "open_questions": list(self.open_questions),
            "todos": list(self.todos),
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "tool_summaries": list(self.tool_summaries),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryDelta":
        if not isinstance(data, dict):
            return cls()
        return cls(
            goals=_string_list(data.get("goals")),
            constraints=_string_list(data.get("constraints")),
            facts=[_fact(item) for item in _dict_list(data.get("facts"))],
            decisions=[_decision(item) for item in _dict_list(data.get("decisions"))],
            open_questions=_string_list(data.get("open_questions")),
            todos=_string_list(data.get("todos")),
            artifact_refs=[_artifact_ref(item) for item in _dict_list(data.get("artifact_refs"))],
            tool_summaries=_string_list(data.get("tool_summaries")),
            warnings=_string_list(data.get("warnings")),
        )


@dataclass
class ParsedModelOutput:
    assistant_response: str
    next_action: dict[str, Any] | None
    memory_delta: MemoryDelta


class MemoryDeltaParser:
    """Parse the single-model structured response protocol."""

    def __init__(self, max_item_chars: int = 500, max_items: int = 40) -> None:
        self.max_item_chars = max_item_chars
        self.max_items = max_items

    def parse(self, output: str | dict[str, Any]) -> ParsedModelOutput:
        if isinstance(output, dict):
            data = dict(output)
        else:
            text = str(output or "").strip()
            try:
                loaded = json.loads(_strip_code_fence(text))
                data = dict(loaded) if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                return ParsedModelOutput(assistant_response=text, next_action=None, memory_delta=MemoryDelta())
        assistant_response = _clean_text(data.get("assistant_response") or data.get("response") or data.get("content") or "")
        if not assistant_response and not isinstance(output, dict):
            assistant_response = str(output or "").strip()
        next_action = data.get("next_action")
        if not isinstance(next_action, dict):
            next_action = None
        raw_delta = data.get("memory_delta")
        delta_data = _normalize_delta_keys(raw_delta) if isinstance(raw_delta, dict) else {}
        delta = self._sanitize_delta(MemoryDelta.from_dict(delta_data))
        return ParsedModelOutput(assistant_response=assistant_response, next_action=next_action, memory_delta=delta)

    def _sanitize_delta(self, delta: MemoryDelta) -> MemoryDelta:
        delta.goals = self._strings(delta.goals)
        delta.constraints = self._strings(delta.constraints)
        delta.open_questions = self._strings(delta.open_questions)
        delta.todos = self._strings(delta.todos)
        delta.tool_summaries = self._strings(delta.tool_summaries)
        delta.warnings = self._strings(delta.warnings)
        delta.facts = [
            Fact(
                content=_shorten(item.content, self.max_item_chars),
                source=_shorten(item.source or "assistant", 80),
                confidence=_bounded_float(item.confidence, 0.0, 1.0, 0.75),
                importance=_bounded_float(item.importance, 0.0, 1.0, 0.5),
                evidence_ref=_shorten(item.evidence_ref or "", 180) or None,
            )
            for item in delta.facts
            if _clean_text(item.content)
        ][: self.max_items]
        delta.decisions = [
            DeltaDecision(
                content=_shorten(item.content, self.max_item_chars),
                reason=_shorten(item.reason, self.max_item_chars),
                confidence=_bounded_float(item.confidence, 0.0, 1.0, 0.75),
                source=_shorten(item.source or "assistant", 80),
            )
            for item in delta.decisions
            if _clean_text(item.content)
        ][: self.max_items]
        delta.artifact_refs = [
            ArtifactRef(
                result_id=_shorten(item.result_id, 160),
                tool_name=_shorten(item.tool_name, 120),
                artifact_type=_shorten(item.artifact_type or "text", 40),
                path=_shorten(item.path, 400),
                summary=_shorten(item.summary, self.max_item_chars),
                token_count=max(0, int(item.token_count or 0)),
            )
            for item in delta.artifact_refs
            if _clean_text(item.result_id) or _clean_text(item.path)
        ][: self.max_items]
        return delta

    def _strings(self, values: list[str]) -> list[str]:
        return [_shorten(item, self.max_item_chars) for item in values if _clean_text(item)][: self.max_items]


def _fact(data: dict[str, Any]) -> Fact:
    return Fact(
        content=str(data.get("content", "")),
        source=str(data.get("source", "assistant")),
        confidence=_bounded_float(data.get("confidence"), 0.0, 1.0, 0.75),
        importance=_bounded_float(data.get("importance"), 0.0, 1.0, 0.5),
        evidence_ref=str(data.get("evidence_ref") or "") or None,
    )


def _decision(data: dict[str, Any]) -> DeltaDecision:
    return DeltaDecision(
        content=str(data.get("content", "")),
        reason=str(data.get("reason", "")),
        confidence=_bounded_float(data.get("confidence"), 0.0, 1.0, 0.75),
        source=str(data.get("source", "assistant")),
    )


def _artifact_ref(data: dict[str, Any]) -> ArtifactRef:
    return ArtifactRef(
        result_id=str(data.get("result_id", "")),
        tool_name=str(data.get("tool_name", "")),
        artifact_type=str(data.get("artifact_type", "text")),
        path=str(data.get("path", "")),
        summary=str(data.get("summary", "")),
        token_count=int(data.get("token_count") or 0),
    )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _shorten(value: Any, max_chars: int) -> str:
    text = _clean_text(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _bounded_float(value: Any, low: float, high: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _normalize_delta_keys(data: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "goal": "goals",
        "goals": "goals",
        "constraint": "constraints",
        "constraints": "constraints",
        "fact": "facts",
        "facts": "facts",
        "decision": "decisions",
        "decisions": "decisions",
        "open_question": "open_questions",
        "open_questions": "open_questions",
        "todo": "todos",
        "todos": "todos",
        "artifact_ref": "artifact_refs",
        "artifact_refs": "artifact_refs",
        "tool_summary": "tool_summaries",
        "tool_summaries": "tool_summaries",
        "warning": "warnings",
        "warnings": "warnings",
    }
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        normalized_key = aliases.get(str(key).strip().lower(), key)
        normalized[normalized_key] = value
    return normalized
