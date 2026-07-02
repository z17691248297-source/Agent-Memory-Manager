from __future__ import annotations

import json
import sys
import types
import urllib.error

from agentmem.runtime.llm_client import OpenAICompatibleClient
from agentmem.vllm.agent_meta import AgentMetaBuilder
from agentmem.vllm.cache_stats import CacheStatsCollector


def test_agent_meta_builder_defaults() -> None:
    builder = AgentMetaBuilder(agent_id="agentmem_benchmark", default_ttl=300)

    system = builder.build(run_id="run_1", stage="planning", segment_type="system")
    shared = builder.build(run_id="run_1", stage="planning", segment_type="shared_prefix")
    tool_result = builder.build(run_id="run_1", stage="tool_calling", segment_type="tool_result")
    scratchpad = builder.build(run_id="run_1", stage="reflection", segment_type="scratchpad")
    expired = builder.build(run_id="run_1", stage="branching", segment_type="expired_branch")

    assert system["priority"] == "high"
    assert shared["priority"] == "high"
    assert tool_result["priority"] in {"normal", "low"}
    assert scratchpad["priority"] == "low"
    assert expired["priority"] == "drop"
    assert system["session_id"] == "run_1"
    assert system["context_id"] == "run_1:planning:system"
    assert system["ttl"] == 300


def test_llm_client_sends_agent_meta_extra_body(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            usage = types.SimpleNamespace(prompt_tokens=3, completion_tokens=2)
            message = types.SimpleNamespace(content="ok")
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice], usage=usage)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    client = OpenAICompatibleClient(
        backend="vllm",
        enable_agent_meta=True,
        agent_meta_builder=AgentMetaBuilder("agentmem_benchmark"),
        stream=False,
    )

    response = client.chat([{"role": "user", "content": "hi"}], run_id="run_1", stage="planning")

    assert response["content"] == "ok"
    assert calls
    assert calls[0]["extra_body"]["agent_meta"]["agent_id"] == "agentmem_benchmark"
    assert calls[0]["extra_body"]["agent_meta"]["session_id"] == "run_1"
    assert calls[0]["extra_body"]["agent_meta"]["segment_type"] == "scratchpad"


def test_llm_client_omits_extra_body_when_agent_meta_disabled(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            usage = types.SimpleNamespace(prompt_tokens=3, completion_tokens=2)
            message = types.SimpleNamespace(content="ok")
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice], usage=usage)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    client = OpenAICompatibleClient(
        backend="vllm",
        enable_agent_meta=False,
        agent_meta_builder=AgentMetaBuilder("agentmem_benchmark"),
        stream=False,
    )

    client.chat([{"role": "user", "content": "hi"}], run_id="run_1", stage="planning")

    assert calls
    assert "extra_body" not in calls[0]


def test_cache_stats_collector_success_and_flatten(monkeypatch) -> None:
    payload = {
        "total_blocks": 128,
        "agent_sessions": 3,
        "segments": {
            "tool_result": {"blocks": 11},
            "shared_prefix": {"blocks": 7},
            "scratchpad": {"blocks": 5},
            "expired_branch": {"blocks": 2},
        },
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=10: FakeResponse())
    stats = CacheStatsCollector("http://example/cache_stats").fetch()

    assert stats["available"] is True
    assert stats["cache_total_blocks"] == 128
    assert stats["cache_agent_sessions"] == 3
    assert stats["cache_tool_result_blocks"] == 11
    assert stats["cache_shared_prefix_blocks"] == 7
    assert stats["cache_scratchpad_blocks"] == 5
    assert stats["cache_expired_branch_blocks"] == 2


def test_cache_stats_collector_failure_and_missing_fields(monkeypatch) -> None:
    collector = CacheStatsCollector("http://example/cache_stats")
    flattened = collector.flatten({"unexpected": {"shape": True}})

    assert flattened["cache_total_blocks"] == -1
    assert flattened["cache_tool_result_blocks"] == -1

    def raise_url_error(url, timeout=10):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)
    stats = collector.fetch()

    assert stats["available"] is False
    assert "offline" in stats["unavailable_reason"]
