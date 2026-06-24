from __future__ import annotations

from agentmem.memory.baseline_memory import BaselineMemory
from agentmem.memory.optimized_memory import OptimizedMemory
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.tools.result import ToolResult
from agentmem.tools.tool_registry import build_default_registry


def test_optimized_memory_externalizes_tool_raw_result(tmp_path) -> None:
    registry = build_default_registry("skills")
    store = ToolResultStore(tmp_path / "tool_store")
    raw = "ERROR CUDA OOM\n" * 200
    result = store.save(
        ToolResult(
            result_id="result_test",
            tool_name="log_analyzer",
            status="success",
            raw_result=raw,
            summary="日志摘要: ERROR CUDA OOM",
            raw_token_len=1000,
            summary_token_len=8,
            raw_path=None,
            chunks=[],
            latency=0.0,
        )
    )

    memory = OptimizedMemory("system", registry, store)
    memory.add_user_message("请分析日志。")
    memory.add_tool_result(result)
    prompt = memory.build_messages(stage="tool_calling", selected_tools=["log_analyzer"])[0]["content"]

    assert "result_id: result_test" in prompt
    assert "日志摘要: ERROR CUDA OOM" in prompt
    assert raw not in prompt
    assert memory.latest_metrics_hint()["injected_tool_tokens"] == 8


def test_baseline_memory_injects_tool_raw_result(tmp_path) -> None:
    registry = build_default_registry("skills")
    raw = "RAW TOOL OUTPUT"
    result = ToolResult(
        result_id="result_baseline",
        tool_name="log_analyzer",
        status="success",
        raw_result=raw,
        summary="summary",
        raw_token_len=20,
        summary_token_len=2,
        raw_path=None,
        chunks=[],
        latency=0.0,
    )

    memory = BaselineMemory("system", registry)
    memory.add_user_message("请分析日志。")
    memory.add_tool_result(result)
    prompt = memory.build_messages(stage="tool_calling", selected_tools=["log_analyzer"])[0]["content"]

    assert raw in prompt
