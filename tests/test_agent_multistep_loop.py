from __future__ import annotations

import json

from agentmem.event_memory.integration import EventSourcedMemoryAdapter
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.runtime.agent import AgentRuntime
from agentmem.runtime.factory import PROJECT_ROOT, SYSTEM_PROMPT
from agentmem.tools.executor import ToolExecutor
from agentmem.tools.tool_registry import build_default_registry


class StepLLM:
    model = "local-step"

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[dict[str, str]]) -> dict:
        self.calls += 1
        if self.calls == 1:
            payload = {
                "assistant_response": "需要调用计算工具。",
                "next_action": {"type": "tool_call", "tool": "calculator", "args": {"input": "1+1"}},
                "memory_delta": {
                    "goals": ["完成一个两步计算任务"],
                    "facts": [
                        {
                            "content": "用户要求计算 1+1",
                            "source": "local-step",
                            "confidence": 0.9,
                            "importance": 0.8,
                        }
                    ],
                },
            }
        else:
            payload = {
                "assistant_response": "最终答案：1+1=2。",
                "next_action": {"type": "final"},
                "memory_delta": {
                    "decisions": [
                        {
                            "content": "返回计算结果 2",
                            "reason": "calculator result",
                            "confidence": 0.95,
                            "source": "local-step",
                        }
                    ]
                },
            }
        content = json.dumps(payload, ensure_ascii=False)
        return {
            "content": content,
            "latency": 0.01,
            "ttft": 0.001,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "tokens_per_second": 500,
            "model": self.model,
        }


def test_agent_runtime_executes_next_action_tool_loop(tmp_path) -> None:
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
    runtime = AgentRuntime(
        memory=memory,
        tools=registry,
        llm_client=StepLLM(),
        tool_executor=ToolExecutor(registry, store),
        max_steps=3,
        enable_next_action_loop=True,
    )

    answer, metrics = runtime.run("请计算 1+1", stage="tool_calling")

    assert answer == "最终答案：1+1=2。"
    assert metrics["agent_steps"] == 2
    assert metrics["tool_names"] == "calculator"
    assert metrics["memory_delta_count"] >= 2
    assert any(fact.content == "用户要求计算 1+1" for fact in memory.state.facts)
    assert any(decision.content == "返回计算结果 2" for decision in memory.state.decisions)
    assert memory.state.artifact_refs
    assert (tmp_path / "tool_store" / "raw").exists()
