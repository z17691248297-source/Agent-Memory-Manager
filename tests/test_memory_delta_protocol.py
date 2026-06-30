from __future__ import annotations

import json

from agentmem.event_memory.memory_delta import MemoryDeltaParser


def test_memory_delta_parser_accepts_valid_json() -> None:
    parser = MemoryDeltaParser(max_item_chars=20)
    output = json.dumps(
        {
            "assistant_response": "ok",
            "next_action": {"type": "tool_call", "tool": "calculator", "args": {"input": "2+2"}},
            "memory_delta": {
                "goals": ["solve"],
                "facts": [
                    {
                        "content": "important fact",
                        "source": "test",
                        "confidence": 1.2,
                        "importance": -1,
                    }
                ],
            },
        }
    )

    parsed = parser.parse(output)

    assert parsed.assistant_response == "ok"
    assert parsed.next_action == {"type": "tool_call", "tool": "calculator", "args": {"input": "2+2"}}
    assert parsed.memory_delta.goals == ["solve"]
    assert parsed.memory_delta.facts[0].confidence == 1.0
    assert parsed.memory_delta.facts[0].importance == 0.0


def test_memory_delta_parser_fallbacks_on_invalid_json() -> None:
    parsed = MemoryDeltaParser().parse("plain assistant text")

    assert parsed.assistant_response == "plain assistant text"
    assert parsed.next_action is None
    assert parsed.memory_delta.is_empty()


def test_memory_delta_parser_ignores_non_object_delta() -> None:
    parsed = MemoryDeltaParser().parse(
        json.dumps(
            {
                "assistant_response": "ok",
                "next_action": "final",
                "memory_delta": ["not", "an", "object"],
            }
        )
    )

    assert parsed.assistant_response == "ok"
    assert parsed.next_action is None
    assert parsed.memory_delta.is_empty()
