from __future__ import annotations

from agentmem.event_memory.evidence import ArtifactContextManager
from agentmem.event_memory.memory_delta import ArtifactRef


def test_artifact_context_finds_term_snippet(tmp_path) -> None:
    path = tmp_path / "tool.txt"
    path.write_text("prefix\nimportant project fact appears in artifact\nsuffix", encoding="utf-8")
    manager = ArtifactContextManager()
    manager.register_artifact(
        ArtifactRef(
            result_id="artifact_1",
            tool_name="reader",
            artifact_type="text",
            path=str(path),
            summary="summary mentions project fact",
            token_count=10,
        )
    )

    refs = manager.search_artifacts(["project fact"])
    context = manager.create_artifact_context(["project fact"], max_tokens_per_ref=64)

    assert refs[0].result_id == "artifact_1"
    assert "project fact" in context
    assert manager.context_load_count == 1
    assert manager.context_tokens > 0
