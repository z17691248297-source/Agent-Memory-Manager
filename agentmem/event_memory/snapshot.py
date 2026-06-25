from __future__ import annotations

import json
import re
from pathlib import Path

from agentmem.event_memory.event import AgentEvent
from agentmem.event_memory.projector import MemoryProjector
from agentmem.event_memory.schema import TaskStateView


class MemorySnapshotStore:
    """Persist TaskStateView snapshots for faster event-log recovery."""

    def __init__(self, root_dir: str | Path = "results/event_memory_snapshots", interval: int = 10) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.interval = max(1, int(interval))
        self.snapshot_count = 0

    def maybe_save(self, run_id: str, state: TaskStateView, event_count: int) -> Path | None:
        if event_count <= 0 or event_count % self.interval != 0:
            return None
        return self.save(run_id, state, event_count)

    def save(self, run_id: str, state: TaskStateView, event_count: int) -> Path:
        path = self.root_dir / f"{run_id}_round_{event_count}.json"
        payload = {
            "run_id": run_id,
            "event_count": event_count,
            "round": state.last_updated_round,
            "state": state.to_dict(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.snapshot_count += 1
        return path

    def latest_snapshot(self, run_id: str) -> tuple[TaskStateView, int] | None:
        paths = sorted(self.root_dir.glob(f"{run_id}_round_*.json"), key=_snapshot_event_count)
        if not paths:
            return None
        path = paths[-1]
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TaskStateView.from_dict(payload.get("state") or {}), int(payload.get("event_count", 0) or 0)

    def restore(self, run_id: str, events: list[AgentEvent], projector: MemoryProjector) -> TaskStateView:
        latest = self.latest_snapshot(run_id)
        if latest is None:
            return projector.replay(events)
        state, event_count = latest
        return projector.replay(events[event_count:], initial_state=state)


def _snapshot_event_count(path: Path) -> int:
    match = re.search(r"_round_(\d+)\.json$", path.name)
    return int(match.group(1)) if match else 0
