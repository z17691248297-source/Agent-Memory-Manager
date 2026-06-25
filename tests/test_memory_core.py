from __future__ import annotations

import json

from agentmem.memory.baseline_memory import BaselineMemory
from agentmem.memory.optimized_memory import OptimizedMemory
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.tools.result import ToolResult
from agentmem.tools.log_summary import analyze_log_text
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


def test_tool_store_keeps_full_raw_and_indexes_chunks(tmp_path) -> None:
    store = ToolResultStore(tmp_path / "tool_store", chunk_chars=80)
    raw = "\n".join(
        [
            "INFO warmup",
            "ERROR CUDA OOM while allocating tensor",
            "WARN timeout waiting for worker",
            "ERROR KV cache allocation failed in block manager",
            "exception failed during retry",
        ]
    )
    summary = store.summarize(raw, "log_analyzer")
    saved = store.save(
        ToolResult(
            result_id="result_full_raw",
            tool_name="log_analyzer",
            status="success",
            raw_result=raw,
            summary=summary,
            raw_token_len=1,
            summary_token_len=1,
            raw_path=None,
            chunks=[],
            latency=0.0,
            metadata={"display_max_output_chars": 20, "display_truncated": True},
        )
    )

    raw_path = tmp_path / "tool_store" / "raw" / "result_full_raw.txt"
    index_path = tmp_path / "tool_store" / "index" / "result_full_raw.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    structured_summary = json.loads(summary)

    assert raw_path.read_text(encoding="utf-8") == raw
    assert saved.raw_token_len > 1
    assert structured_summary["total_lines"] == 5
    assert structured_summary["error_groups"]
    assert "root_cause_candidates" in structured_summary
    assert index["raw_result"] == ""
    assert index["chunks"]
    first_chunk = index["chunks"][0]
    assert {"chunk_id", "result_id", "start_line", "end_line", "token_count", "tags", "signatures", "summary"}.issubset(first_chunk)


def test_baseline_prompt_display_truncates_without_changing_raw() -> None:
    registry = build_default_registry("skills")
    raw = "X" * 120
    result = ToolResult(
        result_id="display_limit",
        tool_name="log_analyzer",
        status="success",
        raw_result=raw,
        summary="summary",
        raw_token_len=30,
        summary_token_len=2,
        raw_path="/tmp/full_raw.txt",
        chunks=[],
        latency=0.0,
        metadata={"display_max_output_chars": 12, "display_truncated": True},
    )

    memory = BaselineMemory("system", registry)
    memory.add_tool_result(result)
    prompt = memory.build_messages(stage="tool_calling", selected_tools=["log_analyzer"])[0]["content"]

    assert "X" * 12 in prompt
    assert raw not in prompt
    assert result.raw_result == raw


def test_log_summary_groups_signatures() -> None:
    summary = analyze_log_text(
        "\n".join(
            [
                "ERROR CUDA OOM rank=0",
                "ERROR CUDA OOM rank=1",
                "WARN timeout after 30s",
                "ERROR KV cache allocation failed block=7",
            ]
        )
    )

    assert summary["total_lines"] == 4
    assert summary["severity_counts"]["ERROR"] == 3
    signatures = {group["signature"] for group in summary["error_groups"]}
    assert "CUDA OOM + OOM" in signatures
    assert any("KV cache allocation failed" in candidate for candidate in summary["root_cause_candidates"])
