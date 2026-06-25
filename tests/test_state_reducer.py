from __future__ import annotations

from agentmem.event_memory.memory_delta import Fact
from agentmem.event_memory.reducer import StateReducer
from agentmem.event_memory.schema import TaskStateView


def test_state_reducer_merges_duplicate_facts_and_keeps_important() -> None:
    state = TaskStateView(
        facts=[
            Fact(content="same fact", source="tool", confidence=0.6, importance=0.4),
            Fact(content="same fact", source="tool", confidence=0.9, importance=0.8),
            Fact(content="other fact", source="assistant", confidence=0.7, importance=0.5),
        ]
    )

    reduced = StateReducer().reduce(state)

    assert len(reduced.facts) == 2
    assert reduced.facts[0].content == "same fact"
    assert reduced.facts[0].confidence == 0.9
