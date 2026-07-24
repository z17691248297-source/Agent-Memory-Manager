from __future__ import annotations

from agentmem.event_memory.memory_delta import Fact
from agentmem.event_memory.reducer import StateReducer
from agentmem.event_memory.schema import TaskStateView


def test_protected_fact_survives_reduction():
    state = TaskStateView(facts=[Fact(content=f"ordinary {i}", importance=0.1) for i in range(10)])
    state.facts.append(Fact(content="must keep", fact_id="f_keep", fact_type="user_constraints", protected=True, importance=1.0))

    reduced = StateReducer(max_facts=3).reduce(state)

    assert any(fact.fact_id == "f_keep" and fact.protected for fact in reduced.facts)


def test_conflicting_fact_preserves_version():
    state = TaskStateView(
        facts=[
            Fact(content="decision is A", fact_id="f1", fact_type="confirmed_decisions", protected=True, version=1),
            Fact(content="decision is B", fact_id="f2", fact_type="confirmed_decisions", version=1),
        ]
    )

    reduced = StateReducer(max_facts=5).reduce(state)
    conflict = next(fact for fact in reduced.facts if fact.fact_id == "f2")

    assert conflict.conflict is True
    assert conflict.version == 2
    assert conflict.supersedes == "f1"
