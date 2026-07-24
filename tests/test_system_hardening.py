from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentmem.benchmark import _task_tool_context
from agentmem.event_memory.integration import EventSourcedMemoryAdapter
from agentmem.event_memory.memory_delta import MemoryDelta
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.runtime.factory import PROJECT_ROOT, SYSTEM_PROMPT
from agentmem.runtime.llm_client import OpenAICompatibleClient
from agentmem.tools.executor import ToolExecutor
from agentmem.tools.log_analyzer import analyze_logs
from agentmem.tools.registry import ToolRegistry
from agentmem.tools.spec import ToolSpec
from agentmem.tools.tool_registry import build_default_registry


def _slow_handler(input_text: str, context: dict | None) -> str:
    time.sleep(1.0)
    return input_text


def _echo_handler(input_text: str, context: dict | None) -> str:
    return input_text


def _registry_with_handler(name: str, handler, timeout_seconds: float, cacheable: bool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name=name,
            category="test",
            brief_description=name,
            full_description=None,
            input_schema={},
            output_schema={},
            skill_path="",
            permission_level="compute_only",
            timeout_seconds=timeout_seconds,
            cacheable=cacheable,
        ),
        handler,
    )
    return registry


def test_tool_timeout_terminates_execution(tmp_path) -> None:
    registry = _registry_with_handler("slow", _slow_handler, timeout_seconds=0.05, cacheable=False)
    executor = ToolExecutor(registry, ToolResultStore(tmp_path / "store"))

    started = time.perf_counter()
    result = executor.execute("slow", "payload")
    elapsed = time.perf_counter() - started

    assert result.status == "timeout"
    assert elapsed < 0.5


def test_tool_cache_returns_isolated_result(tmp_path) -> None:
    registry = _registry_with_handler("echo", _echo_handler, timeout_seconds=1, cacheable=True)
    executor = ToolExecutor(registry, ToolResultStore(tmp_path / "store"))

    first = executor.execute("echo", "payload")
    second = executor.execute("echo", "payload")

    assert first is not second
    assert first.metadata["cache_hit"] is False
    assert second.metadata["cache_hit"] is True
    assert first.result_id == second.result_id


def test_log_analyzer_rejects_path_outside_project() -> None:
    with pytest.raises(PermissionError):
        analyze_logs("dataset: /etc/passwd")


def test_benchmark_context_does_not_expose_evaluator_requirements() -> None:
    context = _task_tool_context(
        {
            "dataset": "benchmarks/fixtures/sample.txt",
            "required_facts": ["secret expected fact"],
            "required_answer_points": ["secret answer point"],
        }
    )

    assert context == {"dataset": "benchmarks/fixtures/sample.txt"}


def test_event_memory_restores_existing_run(tmp_path) -> None:
    registry = build_default_registry(PROJECT_ROOT / "skills")
    store = ToolResultStore(tmp_path / "tool_store")
    memory = EventSourcedMemoryAdapter(
        system_prompt=SYSTEM_PROMPT,
        tool_registry=registry,
        result_store=store,
        output_dir=tmp_path,
        snapshot_interval=1,
    )
    memory.start_round(1, "planning", "remember this")
    memory.add_user_message("remember this")
    memory.record_memory_delta(MemoryDelta(goals=["restore goal"]))
    memory.add_assistant_message("recorded")

    restored = EventSourcedMemoryAdapter(
        system_prompt=SYSTEM_PROMPT,
        tool_registry=registry,
        result_store=store,
        output_dir=tmp_path,
        snapshot_interval=1,
        run_id=memory.run_id,
    )

    assert restored.event_count == memory.event_count
    assert restored.current_round == 1
    assert restored.state.goals == ["restore goal"]
    assert [message["role"] for message in restored.messages] == ["user", "assistant"]


def test_openai_client_is_reused(monkeypatch) -> None:
    created = 0

    class FakeCompletions:
        def create(self, **kwargs):
            usage = SimpleNamespace(prompt_tokens=3, completion_tokens=2)
            message = SimpleNamespace(content="ok")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            nonlocal created
            created += 1
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    client = OpenAICompatibleClient(base_url="http://example.invalid/v1", model="fake")

    client.chat([{"role": "user", "content": "one"}])
    client.chat([{"role": "user", "content": "two"}])

    assert created == 1
