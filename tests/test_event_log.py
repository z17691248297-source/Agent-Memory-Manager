from __future__ import annotations

from agentmem.event_memory.event import AgentEvent
from agentmem.event_memory.event_log import EventLog


def test_event_log_append_load_replay(tmp_path) -> None:
    log = EventLog(tmp_path / "event_log")
    event = AgentEvent(
        event_id="evt_1",
        run_id="run_1",
        session_id="session_1",
        round=1,
        stage="planning",
        event_type="user_message",
        content="请分析 AgentMem。",
        source="user",
    )

    log.append(event)

    loaded = EventLog(tmp_path / "event_log").load("run_1")
    replayed = EventLog(tmp_path / "event_log").replay("run_1")
    assert loaded[0].event_id == "evt_1"
    assert replayed[0].content == "请分析 AgentMem。"
    assert (tmp_path / "event_log" / "run_1.jsonl").read_text(encoding="utf-8").count("\n") == 1
