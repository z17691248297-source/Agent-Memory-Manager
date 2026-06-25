from __future__ import annotations

import json
from pathlib import Path

from agentmem.event_memory.event import AgentEvent


class EventLog:
    """Append-only JSONL event log stored under results/event_log."""

    def __init__(self, root_dir: str | Path = "results/event_log", max_inline_tool_tokens: int = 512) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.max_inline_tool_tokens = max_inline_tool_tokens
        self._events: dict[str, list[AgentEvent]] = {}

    def append(self, event: AgentEvent) -> AgentEvent:
        event = self._sanitize_event(event)
        events = self._events.setdefault(event.run_id, [])
        events.append(event)
        path = self._path(event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def list_events(self, run_id: str) -> list[AgentEvent]:
        if run_id not in self._events:
            self._events[run_id] = self.load(run_id)
        return list(self._events[run_id])

    def replay(self, run_id: str) -> list[AgentEvent]:
        return self.list_events(run_id)

    def load(self, run_id: str) -> list[AgentEvent]:
        path = self._path(run_id)
        if not path.exists():
            return []
        events: list[AgentEvent] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(AgentEvent.from_dict(json.loads(stripped)))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid event log JSON at {path}:{line_number}") from exc
        self._events[run_id] = events
        return list(events)

    def save(self, run_id: str) -> Path:
        path = self._path(run_id)
        events = self._events.get(run_id, [])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for event in events:
                file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return path

    def _path(self, run_id: str) -> Path:
        return self.root_dir / f"{run_id}.jsonl"

    def _sanitize_event(self, event: AgentEvent) -> AgentEvent:
        metadata = dict(event.metadata or {})
        metadata.pop("raw_result", None)
        metadata.pop("raw_content", None)
        event.metadata = metadata
        if (
            event.event_type == "tool_result"
            and event.content
            and event.content_path
            and event.token_count > self.max_inline_tool_tokens
        ):
            event.content = event.content[: self.max_inline_tool_tokens * 4] + "\n[content truncated; use content_path/evidence_ref]"
        return event
