from __future__ import annotations

from agentmem.event_memory.renderer import MemoryViewRenderer
from agentmem.event_memory.memory_delta import ArtifactRef, Fact
from agentmem.event_memory.schema import TaskStateView


def test_renderer_uses_artifact_summary_not_raw_tool_content() -> None:
    raw = "RAW_TOOL_CONTENT_SHOULD_NOT_RENDER " * 50
    state = TaskStateView(
        goals=["analyze task"],
        facts=[Fact(content="important tool fact", source="tool", confidence=0.9, importance=0.8)],
        artifact_refs=[
            ArtifactRef(
                result_id="tool_1",
                tool_name="reader",
                artifact_type="text",
                path="/tmp/log.txt",
                summary="bounded artifact summary",
                token_count=100,
            )
        ],
    )

    rendered = MemoryViewRenderer().render(state, recent_turns=[], current_query="当前问题")

    assert "bounded artifact summary" in rendered
    assert "result_id=tool_1" in rendered
    assert raw not in rendered
    assert "state_view_tokens:" in rendered
