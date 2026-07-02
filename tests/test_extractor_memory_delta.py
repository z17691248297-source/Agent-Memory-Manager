from __future__ import annotations

import json

from agentmem.event_memory.extractor import ExternalMemoryDeltaExtractor, ExtractorConfig
from agentmem.event_memory.integration import EventSourcedMemoryAdapter
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.runtime.agent import AgentRuntime
from agentmem.runtime.factory import PROJECT_ROOT, SYSTEM_PROMPT
from agentmem.tools.executor import ToolExecutor
from agentmem.tools.tool_registry import build_default_registry


class PlainLLM:
    model = "plain-main"

    def chat(self, messages: list[dict[str, str]], **_: object) -> dict:
        return {
            "content": "已完成日志判断。",
            "latency": 0.01,
            "ttft": 0.001,
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "total_tokens": 13,
            "tokens_per_second": 100,
            "model": self.model,
        }


class MockExtractorClient:
    def chat(self, messages: list[dict[str, str]], temperature: float = 0, max_tokens: int = 1024) -> dict:
        content = json.dumps(
            {
                "memory_delta": {
                    "facts": [
                        {
                            "content": "extractor generated structured fact",
                            "source": "mock_extractor",
                            "confidence": 0.9,
                            "importance": 0.8,
                        }
                    ],
                    "tool_summaries": ["tool summary from extractor"],
                }
            }
        )
        return {"content": content}


def test_mock_extractor_updates_task_state_view(tmp_path) -> None:
    registry = build_default_registry(PROJECT_ROOT / "skills")
    store = ToolResultStore(tmp_path / "tool_store")
    memory = EventSourcedMemoryAdapter(
        system_prompt=SYSTEM_PROMPT,
        tool_registry=registry,
        result_store=store,
        output_dir=tmp_path,
        recent_rounds=2,
        mode="optimized",
    )
    extractor = ExternalMemoryDeltaExtractor(
        ExtractorConfig(enabled=True, base_url="http://127.0.0.1:9000/v1", model="mock")
    )
    extractor.client = MockExtractorClient()
    extractor._available = True
    runtime = AgentRuntime(
        memory=memory,
        tools=registry,
        llm_client=PlainLLM(),
        tool_executor=ToolExecutor(registry, store),
        memory_delta_extractor=extractor,
        max_steps=1,
        enable_next_action_loop=False,
    )

    answer, metrics = runtime.run("请记录当前任务状态", stage="planning")

    assert answer == "已完成日志判断。"
    assert metrics["extractor_calls"] == 1
    assert metrics["memory_delta_count"] == 1
    assert any(fact.content == "extractor generated structured fact" for fact in memory.state.facts)
    assert "tool summary from extractor" in memory.state.tool_summaries
