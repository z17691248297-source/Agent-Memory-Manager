from __future__ import annotations

from agentmem.event_memory.event import AgentEvent
from agentmem.event_memory.memory_delta import ArtifactRef, Fact, MemoryDelta
from agentmem.event_memory.projector import MemoryProjector


def test_tool_result_event_records_artifact_ref(tmp_path) -> None:
    raw_path = tmp_path / "tool.txt"
    raw_path.write_text("raw tool output", encoding="utf-8")
    event = AgentEvent(
        event_id="evt_log",
        run_id="run_1",
        session_id="session_1",
        round=1,
        stage="tool_calling",
        event_type="tool_result",
        content="tool summary",
        content_path=str(raw_path),
        source="generic_tool",
        metadata={
            "tool_name": "generic_tool",
            "result_id": "tool_1",
            "summary": "tool summary",
            "artifacts": [
                {
                    "artifact_type": "text",
                    "path": str(raw_path),
                    "token_count": 3,
                    "description": "tool summary",
                }
            ],
        },
    )

    state = MemoryProjector().replay([event])

    assert state.artifact_refs[0].result_id == "tool_1"
    assert state.artifact_refs[0].path == str(raw_path)
    assert state.tool_summaries == ["tool summary"]


def test_memory_delta_event_updates_task_state() -> None:
    delta = MemoryDelta(
        goals=["ship generic memory"],
        constraints=["no task-specific extraction"],
        facts=[Fact(content="state is updated from memory_delta", source="test", confidence=0.9, importance=0.8)],
        artifact_refs=[ArtifactRef(result_id="r1", tool_name="reader", artifact_type="text", path="/tmp/r1.txt")],
    )
    event = AgentEvent(
        event_id="evt_delta",
        run_id="run_1",
        session_id="session_1",
        round=1,
        stage="planning",
        event_type="memory_delta",
        source="assistant",
        metadata={"memory_delta": delta.to_dict()},
    )

    state = MemoryProjector().replay([event])

    assert state.goals == ["ship generic memory"]
    assert state.constraints == ["no task-specific extraction"]
    assert state.facts[0].content == "state is updated from memory_delta"
    assert state.artifact_refs[0].result_id == "r1"
