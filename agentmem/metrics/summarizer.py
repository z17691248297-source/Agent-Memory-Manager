from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from agentmem.metrics.hardware import collect_hardware_info, collect_os_environment
from agentmem.runtime.factory import PROJECT_ROOT
from agentmem.runtime.llm_factory import load_runtime_config


Rows = list[dict[str, Any]]


def summarize_results(results_dir: str | Path = "results", config_path: str | Path | None = None) -> dict[str, Path]:
    """Generate summary.csv and the formal benchmark report."""
    results = Path(results_dir)
    if not results.is_absolute():
        results = PROJECT_ROOT / results
    results.mkdir(parents=True, exist_ok=True)

    config_file = Path(config_path) if config_path else PROJECT_ROOT / "configs" / "config.yaml"
    config = load_runtime_config(config_file)
    frames = _load_frames(results)

    summary = _build_summary_rows(results)
    summary_path = results / "summary.csv"
    _write_csv(summary_path, summary, _summary_fields())

    report_path = results / "report.md"
    report_path.write_text(_build_report(config, frames), encoding="utf-8")
    return {"summary_csv": summary_path, "report_md": report_path}


def _load_frames(results: Path) -> dict[str, Rows]:
    return {
        "tool_heavy": _concat_existing(results, ["tool_heavy_baseline.csv", "tool_heavy_optimized.csv"]),
        "long_session": _concat_existing(
            results,
            [
                "long_session_full_history.csv",
                "long_session_summary_memory.csv",
                "long_session_event_sourced_memory.csv",
            ],
        ),
        "multi_stage": _concat_existing(
            results,
            [
                "multi_stage_full_history.csv",
                "multi_stage_summary_memory.csv",
                "multi_stage_event_sourced_memory.csv",
            ],
        ),
        "branching": _read_csv(results / "branch_benchmark.csv"),
        "prefix_cache": _concat_existing(results, ["prefix_cache_baseline.csv", "prefix_cache_optimized.csv"]),
        "ablation": _read_csv(results / "ablation.csv"),
        "cache_pressure": _read_csv(results / "cache_pressure.csv"),
        "ttl_priority": _read_csv(results / "ttl_priority.csv"),
    }


def _summary_fields() -> list[str]:
    return [
        "file",
        "scenario",
        "mode",
        "rows",
        "avg_prompt_tokens",
        "avg_output_tokens",
        "avg_total_tokens",
        "avg_latency",
        "avg_ttft",
        "tokens_per_second",
        "peak_gpu_memory_mb",
        "success_rate",
        "avg_score",
        "avg_raw_tool_tokens",
        "avg_injected_tool_tokens",
        "avg_tool_compression_ratio",
        "avg_state_view_tokens",
        "avg_event_count",
        "avg_snapshot_count",
        "avg_branch_saving_ratio",
        "agent_meta_enabled",
        "agent_id",
        "cache_stats_available",
        "cache_stats_unavailable_reason",
        "cache_total_blocks",
        "cache_agent_sessions",
        "cache_tool_result_blocks",
        "cache_shared_prefix_blocks",
        "cache_scratchpad_blocks",
        "cache_expired_branch_blocks",
    ]


def _build_summary_rows(results: Path) -> Rows:
    rows: Rows = []
    for path in sorted(results.glob("*.csv")):
        if path.name == "summary.csv":
            continue
        frame = _read_csv(path)
        if not frame:
            continue
        mode_values = [str(row.get("mode", "")) for row in frame if row.get("mode")]
        unique_modes = sorted(set(mode_values))
        rows.append(
            {
                "file": path.name,
                "scenario": _first_value(frame, "scenario", path.stem),
                "mode": unique_modes[0] if len(unique_modes) == 1 else ("both" if unique_modes else _mode_from_filename(path.name)),
                "rows": len(frame),
                "avg_prompt_tokens": _mean(frame, "prompt_tokens"),
                "avg_output_tokens": _mean(frame, "output_tokens"),
                "avg_total_tokens": _mean(frame, "total_tokens"),
                "avg_latency": _mean(frame, "latency"),
                "avg_ttft": _mean(frame, "ttft"),
                "tokens_per_second": _mean(frame, "tokens_per_second"),
                "peak_gpu_memory_mb": _max(frame, "peak_gpu_memory_mb"),
                "success_rate": _success_rate(frame),
                "avg_score": _mean(frame, "score"),
                "avg_raw_tool_tokens": _mean(frame, "raw_tool_tokens"),
                "avg_injected_tool_tokens": _mean(frame, "injected_tool_tokens"),
                "avg_tool_compression_ratio": _mean(frame, "tool_compression_ratio"),
                "avg_state_view_tokens": _mean(frame, "state_view_tokens"),
                "avg_event_count": _mean(frame, "event_count"),
                "avg_snapshot_count": _mean(frame, "snapshot_count"),
                "avg_branch_saving_ratio": _mean(frame, "branch_saving_ratio"),
                "agent_meta_enabled": _first_value(frame, "agent_meta_enabled", ""),
                "agent_id": _first_value(frame, "agent_id", ""),
                "cache_stats_available": _first_value(frame, "cache_stats_available", ""),
                "cache_stats_unavailable_reason": _first_value(frame, "cache_stats_unavailable_reason", ""),
                "cache_total_blocks": _last_numeric(frame, "cache_total_blocks", -1),
                "cache_agent_sessions": _last_numeric(frame, "cache_agent_sessions", -1),
                "cache_tool_result_blocks": _last_numeric(frame, "cache_tool_result_blocks", -1),
                "cache_shared_prefix_blocks": _last_numeric(frame, "cache_shared_prefix_blocks", -1),
                "cache_scratchpad_blocks": _last_numeric(frame, "cache_scratchpad_blocks", -1),
                "cache_expired_branch_blocks": _last_numeric(frame, "cache_expired_branch_blocks", -1),
            }
        )
    return rows


def _build_report(config: dict[str, Any], frames: dict[str, Rows]) -> str:
    llm = dict(config.get("llm") or {})
    extractor = dict(config.get("extractor") or {})
    memory = dict(config.get("memory") or {})
    benchmark = dict(config.get("benchmark") or {})
    environment = dict(config.get("environment") or {})
    backend = _detect_backend(frames, str(llm.get("backend", "vllm")))
    scenarios = [name for name, rows in frames.items() if rows]
    all_modes = {str(row.get("mode")) for rows in frames.values() for row in rows if row.get("mode")}
    preferred_modes = {
        "baseline",
        "optimized",
        "full_history",
        "summary_memory",
        "event_sourced_memory",
    }
    modes = sorted(mode for mode in all_modes if mode in preferred_modes) or sorted(all_modes)
    hardware = collect_hardware_info()
    os_environment = collect_os_environment()

    parts = [
        "# AgentMem Benchmark Report",
        "",
        "## 1. 项目目标",
        "",
        "AgentMem 是通用轻量 Agent Runtime + Memory Manager，用于让 Agent 通过 memory_delta 主动维护结构化任务状态，并通过 artifact_refs 管理工具结果。Benchmark 只用于评估不同任务场景下的上下文、质量和可追溯性表现；Memory 核心不依赖具体 benchmark 关键词。",
        "",
        "## 2. 实验设置",
        "",
        _settings_table(backend, llm, extractor, memory, benchmark, environment, os_environment, frames, scenarios, modes),
        "",
        "## 3. 系统架构",
        "",
        _architecture_section(),
        "",
        "## 4. Workloads",
        "",
        _workload_section(frames),
        "",
        "## 5. Hardware",
        "",
        _hardware_section(hardware),
        "",
        "## 6. Success / Score",
        "",
        _success_score_section(frames),
        "",
        "## Configured Model Backend Results",
        "",
        _backend_results_section(frames, backend),
        "",
        "## AgentMeta on/off 对比",
        "",
        _agent_meta_section(frames),
        "",
        "## Cache pressure benchmark",
        "",
        _cache_pressure_section(frames["cache_pressure"]),
        "",
        "## TTL/Priority benchmark",
        "",
        _ttl_priority_section(frames["ttl_priority"]),
        "",
        "## cache_stats scope",
        "",
        _cache_stats_scope_section(frames),
        "",
        "## cache_stats 可用性",
        "",
        _cache_stats_availability_section(frames),
        "",
        "## audit_agent_meta.py 审计摘要",
        "",
        _agent_meta_audit_section(frames),
        "",
        "## agent_meta segment 映射",
        "",
        _agent_meta_mapping_section(),
        "",
        "## 7. Tool-heavy 结果",
        "",
        "该场景复现大规模工具输出直接进入 prompt 后造成的上下文膨胀。",
        "",
        _tool_heavy_section(frames["tool_heavy"]),
        "",
        "## 8. Long-session 结果",
        "",
        "该场景复现多轮长生命周期会话中历史上下文持续增长的问题。",
        "",
        _long_session_section(frames["long_session"]),
        "",
        "## 9. Multi-stage 结果",
        "",
        "该场景覆盖 planning -> tool_calling -> reflection -> final_answer 的多阶段智能体流程。",
        "",
        _multi_stage_section(frames["multi_stage"]),
        "",
        "## Event-Sourced Agent Memory",
        "",
        _event_memory_section(frames),
        "",
        "## 10. Branching 结果",
        "",
        "该场景复现分支推理中公共上下文重复复制的问题，并通过 shared_prefix / expired_branch 等 segment_type 将分支基座与过期分支传递给 vLLM cache 管理原型。",
        "",
        _branching_section(frames["branching"]),
        "",
        "## 11. Prefix-cache 结果",
        "",
        "该场景验证稳定 prompt prefix 对 prefix cache 复用、prefill 和 TTFT 的影响。vLLM 后端会尽力读取 /metrics。",
        "",
        _prefix_cache_section(frames["prefix_cache"]),
        "",
        "## 12. Ablation 结果",
        "",
        _ablation_section(frames["ablation"]),
        "",
        "## 13. 指标说明",
        "",
        _metrics_notes_section(),
        "",
        "## 14. 结论",
        "",
        _conclusion(frames),
        "",
    ]
    return "\n".join(parts)


def _settings_table(
    backend: str,
    llm: dict[str, Any],
    extractor: dict[str, Any],
    memory: dict[str, Any],
    benchmark: dict[str, Any],
    environment: dict[str, Any],
    os_environment: dict[str, Any],
    frames: dict[str, Rows],
    scenarios: list[str],
    modes: list[str],
) -> str:
    optimizations = [
        "event_sourced_memory",
        "memory_delta",
        "artifact_refs",
        "stable_renderer",
    ]
    if bool(memory.get("enable_tool_externalization", True)):
        optimizations.append("tool_externalization")
    extractor_stats = _extractor_stats(frames, bool(extractor.get("enabled")))
    rows = [
        {"item": "backend", "value": backend},
        {"item": "model", "value": _display_model(backend, llm)},
        {"item": "client_os", "value": os_environment.get("client_os", "")},
        {"item": "client_environment", "value": os_environment.get("client_environment", "")},
        {"item": "model_server_os", "value": environment.get("model_server_os", "unknown")},
        {"item": "official_os_compatibility_run", "value": os_environment.get("official_os_compatibility_run", False)},
        {"item": "note", "value": os_environment.get("note", "")},
        {"item": "main_llm_backend", "value": llm.get("backend", backend)},
        {"item": "main_llm_base_url", "value": llm.get("base_url", "")},
        {"item": "main_llm_max_model_len", "value": environment.get("main_llm_max_model_len", "unknown")},
        {"item": "agent_meta_enabled", "value": _first_value([row for frame in frames.values() for row in frame], "agent_meta_enabled", "")},
        {"item": "cache_stats_available", "value": _first_value([row for frame in frames.values() for row in frame], "cache_stats_available", "")},
        {"item": "cache_stats_unavailable_reason", "value": _first_value([row for frame in frames.values() for row in frame], "cache_stats_unavailable_reason", "")},
        {"item": "extractor_backend", "value": extractor.get("backend", "disabled") if extractor.get("enabled") else "disabled"},
        {"item": "extractor_model", "value": extractor.get("model", "") if extractor.get("enabled") else ""},
        {"item": "extractor_base_url", "value": extractor.get("base_url", "") if extractor.get("enabled") else ""},
        {"item": "extractor_enabled", "value": extractor_stats["enabled"]},
        {"item": "extractor_effective", "value": extractor_stats["effective"]},
        {"item": "extractor_status", "value": extractor_stats["status"]},
        {"item": "extractor_success_count", "value": extractor_stats["success_count"]},
        {"item": "extractor_failure_count", "value": extractor_stats["failure_count"]},
        {"item": "scenarios", "value": ", ".join(scenarios) if scenarios else "none"},
        {"item": "mode", "value": ", ".join(modes) if modes else "none"},
        {"item": "repeat", "value": benchmark.get("repeat", "")},
        {"item": "recent_rounds", "value": memory.get("recent_rounds", "")},
        {"item": "enabled_optimizations", "value": ", ".join(optimizations)},
    ]
    return _markdown_table(rows, ["item", "value"])


def _display_model(backend: str, llm: dict[str, Any]) -> str:
    return str(llm.get("model", ""))


def _extractor_stats(frames: dict[str, Rows], enabled: bool) -> dict[str, Any]:
    rows = [row for frame in frames.values() for row in frame]
    success_count = int(sum(_to_float(row.get("extractor_success_count"), 0) for row in rows))
    failure_count = int(sum(_to_float(row.get("extractor_failure_count"), 0) for row in rows))
    effective = success_count > 0
    if not enabled:
        status = "disabled"
    elif effective:
        status = "active"
    elif failure_count > 0:
        status = "fallback"
    else:
        status = "unavailable"
    return {
        "enabled": enabled,
        "effective": effective,
        "status": status,
        "success_count": success_count,
        "failure_count": failure_count,
    }


def _workload_section(frames: dict[str, Rows]) -> str:
    task_dir = PROJECT_ROOT / "benchmarks" / "tasks"
    rows: Rows = []
    for scenario, file_name in [
        ("tool-heavy", "tool_heavy.jsonl"),
        ("long-session", "long_session.jsonl"),
        ("multi-stage", "multi_stage.jsonl"),
        ("branching", "branching.jsonl"),
    ]:
        path = task_dir / file_name
        line_count = _count_jsonl_rows(path)
        rows.append(
            {
                "scenario": scenario,
                "workload_file": str(path.relative_to(PROJECT_ROOT)) if path.exists() else "missing",
                "tasks": line_count,
            }
        )
    rows.append({"scenario": "prefix-cache", "workload_file": "metric:prefix-cache", "tasks": len(frames["prefix_cache"])})
    rows.append({"scenario": "ablation", "workload_file": "metric:ablation", "tasks": len(frames["ablation"])})
    rows.append({"scenario": "cache-pressure", "workload_file": "metric:cache-pressure", "tasks": len(frames["cache_pressure"])})
    rows.append({"scenario": "ttl-priority", "workload_file": "metric:ttl-priority", "tasks": len(frames["ttl_priority"])})
    return _markdown_table(rows, ["scenario", "workload_file", "tasks"])


def _architecture_section() -> str:
    return "\n".join(
        [
            "AgentMem 实现了支持典型智能体工作流的轻量 Agent Runtime，并将 Event-Sourced Memory 与 vLLM Agent-aware KV cache 元信息对接为端到端实验路径。",
            "",
            "- AgentRuntime：负责多轮输入、轻量 next_action loop、工具执行、LLM 调用和指标采集。",
            "- Event-Sourced Memory：记录 user_message、tool_call、tool_result、assistant_response、memory_delta、final_answer、metric 等事件。",
            "- memory_delta：主模型响应中可主动写入 goals、constraints、facts、decisions、open_questions、todos、artifact_refs、tool_summaries 和 warnings；未稳定输出时，可选 extractor 只生成同一结构化状态更新，不生成最终回答。",
            "- Task State View：Memory Manager 从事件流投影出的结构化状态，prompt 渲染 Task State View、Artifact References、Recent Context 和 Current Query。",
            "- Tool Store：工具 raw output 保存在 results/tool_store/raw/，prompt 只引用 result_id、summary 和 artifact metadata。",
            "- Stable Renderer：保持 prompt 结构稳定，为 vLLM prefix cache 复用创造条件。",
        ]
    )


def _backend_results_section(frames: dict[str, Rows], backend: str) -> str:
    rows = [row for frame in frames.values() for row in frame if row.get("backend") == backend]
    if not rows:
        return "暂无已配置模型结果。请先运行 `python -m agentmem benchmark --scenario <name>`。"
    grouped = _group(rows, ["scenario", "mode"], {
        "prompt_tokens": "mean",
        "state_view_tokens": "mean",
        "latency": "mean",
        "ttft": "mean",
        "tokens_per_second": "mean",
        "peak_gpu_memory_mb": "max",
        "prefix_cache_hit_rate": "mean",
        "cached_prompt_tokens": "mean",
        "kv_cache_usage": "mean",
        "cache_total_blocks": "max",
        "cache_agent_sessions": "max",
        "cache_tool_result_blocks": "max",
        "cache_shared_prefix_blocks": "max",
        "cache_scratchpad_blocks": "max",
        "cache_expired_branch_blocks": "max",
        "score": "mean",
    })
    for row in grouped:
        group_rows = [item for item in rows if item.get("scenario") == row.get("scenario") and item.get("mode") == row.get("mode")]
        row["success_rate"] = _success_rate(group_rows)
    note = "说明：本节使用 configs/config.yaml 中配置的模型 backend；latency、TTFT、tokens_per_second 和显存字段用于真实性能分析。cache_stats 不可用时 cache 字段为 -1，并记录 unavailable_reason。agent_meta 不进入 prompt，只通过 OpenAI-compatible extra_body 发送。"
    fields = [
        "scenario",
        "mode",
        "prompt_tokens",
        "state_view_tokens",
        "latency",
        "ttft",
        "tokens_per_second",
        "peak_gpu_memory_mb",
        "prefix_cache_hit_rate",
        "cached_prompt_tokens",
        "kv_cache_usage",
        "cache_total_blocks",
        "cache_agent_sessions",
        "cache_tool_result_blocks",
        "cache_shared_prefix_blocks",
        "cache_scratchpad_blocks",
        "cache_expired_branch_blocks",
        "success_rate",
        "score",
    ]
    return "\n\n".join([note, _markdown_table(grouped, fields)])


def _metrics_notes_section() -> str:
    return "\n".join(
        [
            "- vLLM 指标依赖服务端版本和 /v1/agentmem/cache_stats 暴露情况；缺失时报告为 -1，并在 summary/report 中保留 unavailable_reason。",
            "- 远程 vLLM 主模型服务通过 OpenAI-compatible API 提供推理能力，Agent-aware cache_stats 用于观察服务端 KV block 旁路元信息。",
            "- Event-Sourced Memory 使用主模型按协议输出的 memory_delta；extractor 负责将不稳定输出规整为同一结构化状态更新。",
            "- MemoryPlan JSONL 记录每次 LLM 请求前的 run_id、stage、context_id、segment_type、priority、ttl、included/excluded items 和 agent_meta。",
            "- Agent-aware cache 实验关注 Agent 侧阶段、session、context、priority、ttl 与服务端 cache_stats 的关联观测。",
        ]
    )


def _hardware_section(hardware: dict[str, Any]) -> str:
    rows = [{"item": key, "value": value} for key, value in hardware.items()]
    return _markdown_table(rows, ["item", "value"])


def _success_score_section(frames: dict[str, Rows]) -> str:
    rows: Rows = []
    for scenario, frame in frames.items():
        if not frame:
            continue
        for key, group in _group_by(frame, ["mode"]).items():
            rows.append(
                {
                    "scenario": scenario,
                    "mode": key[0],
                    "rows": len(group),
                    "success_rate": _success_rate(group),
                    "avg_score": _mean(group, "score"),
                }
            )
    return _markdown_table(rows, ["scenario", "mode", "rows", "success_rate", "avg_score"]) if rows else "暂无 success/score 数据。"


def _tool_heavy_section(rows: Rows) -> str:
    if not rows:
        return "暂无 tool-heavy 数据。"
    grouped = _group(rows, ["mode"], {
        "prompt_tokens": "mean",
        "raw_tool_tokens": "mean",
        "injected_tool_tokens": "mean",
        "tool_compression_ratio": "mean",
        "latency": "mean",
        "ttft": "mean",
        "peak_gpu_memory_mb": "max",
        "score": "mean",
    })
    text = [_markdown_table(grouped, list(grouped[0].keys()) if grouped else [])]
    reduction = _mode_reduction(rows, "prompt_tokens")
    if reduction is not None:
        text.append(f"\nPrompt token reduction: {reduction:.2f}%.")
    return "\n".join(text)


def _long_session_section(rows: Rows) -> str:
    if not rows:
        return "暂无 long-session 数据。"
    table_rows: Rows = []
    for mode, group in _group_by(rows, ["mode"]).items():
        sorted_group = sorted(group, key=lambda row: _to_float(row.get("round")))
        table_rows.append(
            {
                "mode": mode[0],
                "first_round_prompt_tokens": _first_numeric(sorted_group, "prompt_tokens"),
                "round_10_prompt_tokens": _round_value(sorted_group, 10, "prompt_tokens"),
                "round_20_prompt_tokens": _round_value(sorted_group, 20, "prompt_tokens"),
                "round_50_prompt_tokens": _round_value(sorted_group, 50, "prompt_tokens"),
                "max_history_tokens": _max(sorted_group, "history_tokens"),
                "max_summary_tokens": _max(sorted_group, "summary_tokens"),
                "max_state_view_tokens": _max(sorted_group, "state_view_tokens"),
                "avg_event_count": _mean(sorted_group, "event_count"),
                "max_snapshot_count": _max(sorted_group, "snapshot_count"),
                "early_fact_retention": _mean(sorted_group, "early_fact_retention"),
                "success_rate": _success_rate(sorted_group),
                "avg_score": _mean(sorted_group, "score"),
            }
        )
    reduction = _mode_reduction(_last_rounds(rows), "prompt_tokens")
    suffix = f"\nRound 50 prompt token reduction: {reduction:.2f}%." if reduction is not None else ""
    return _markdown_table(table_rows, list(table_rows[0].keys())) + suffix


def _multi_stage_section(rows: Rows) -> str:
    if not rows:
        return "暂无 multi-stage 数据。"
    grouped = _group(rows, ["mode", "stage"], {
        "prompt_tokens": "mean",
        "state_view_tokens": "mean",
        "event_count": "mean",
        "snapshot_count": "mean",
        "raw_tool_tokens": "mean",
        "injected_tool_tokens": "mean",
        "latency": "mean",
        "early_fact_retention": "mean",
        "score": "mean",
    })
    for row in grouped:
        stage_rows = [item for item in rows if item.get("mode") == row.get("mode") and item.get("stage") == row.get("stage")]
        row["success_rate"] = _success_rate(stage_rows)
    return _markdown_table(grouped, list(grouped[0].keys()) if grouped else [])


def _event_memory_section(frames: dict[str, Rows]) -> str:
    rows: Rows = []
    for scenario, frame_key in [("long-session", "long_session"), ("multi-stage", "multi_stage")]:
        for mode, group in _group_by(frames.get(frame_key, []), ["mode"]).items():
            if mode[0] not in {
                "baseline",
                "optimized",
                "full_history",
                "summary_memory",
                "event_sourced_memory",
            }:
                continue
            rows.append(
                {
                    "scenario": scenario,
                    "memory_mode": mode[0],
                    "prompt_tokens": _mean(group, "prompt_tokens"),
                    "state_view_tokens": _mean(group, "state_view_tokens"),
                    "success_rate": _success_rate(group),
                    "score": _mean(group, "score"),
                    "early_fact_retention": _mean(group, "early_fact_retention"),
                    "snapshot_count": _mean(group, "snapshot_count"),
                    "memory_delta_count": _mean(group, "memory_delta_count"),
                    "fact_count": _mean(group, "fact_count"),
                    "artifact_ref_count": _mean(group, "artifact_ref_count"),
                }
            )
    if not rows:
        return "暂无 event-sourced memory 数据。"

    long_rows = frames.get("long_session", [])
    multi_rows = frames.get("multi_stage", [])
    combined = [*long_rows, *multi_rows]
    token_reduction = _mode_reduction_between(combined, "full_history", "event_sourced_memory", "prompt_tokens")
    retention_delta = _mode_delta(combined, "summary_memory", "event_sourced_memory", "early_fact_retention")
    conclusions = [
        "方法说明：Event Log 记录 Agent 执行事件；主模型响应可输出 memory_delta；当主模型未稳定输出时，可选 extractor 只生成同 schema 的结构化 memory_delta。Memory Manager 将 goals、constraints、facts、decisions、todos 和 artifact_refs 合并为 Task State View；Renderer 只渲染状态视图、artifact metadata 和最近上下文。",
        "对比口径：full_history 注入完整历史和工具结果；summary_memory 使用工具外置和历史摘要；event_sourced_memory 使用模型产生的 memory_delta、artifact_refs 和 Task State View。Benchmark evaluator 可以按任务检查 required_facts，但 Memory 核心不写死任务关键词。",
        _markdown_table(
            rows,
            [
                "scenario",
                "memory_mode",
                "prompt_tokens",
                "state_view_tokens",
                "success_rate",
                "score",
                "early_fact_retention",
                "snapshot_count",
                "memory_delta_count",
                "fact_count",
                "artifact_ref_count",
            ],
        ),
    ]
    if token_reduction is not None:
        conclusions.append(f"结论：event_sourced_memory 相比 full_history 平均 prompt_tokens 降低约 {token_reduction:.2f}%。")
    if retention_delta is not None:
        direction = "更高" if retention_delta >= 0 else "更低"
        conclusions.append(f"早期事实保留：event_sourced_memory 相比 summary_memory 平均 early_fact_retention {direction} {abs(retention_delta):.4f}。")
    return "\n\n".join(conclusions)


def _branching_section(rows: Rows) -> str:
    if not rows:
        return "暂无 branching 数据。"
    grouped = _group(rows, ["mode", "branch_count"], {
        "shared_context_tokens": "mean",
        "branch_delta_tokens": "mean",
        "duplicated_context_tokens": "mean",
        "optimized_context_tokens": "mean",
        "branch_saving_ratio": "mean",
        "latency": "mean",
        "score": "mean",
    })
    return _markdown_table(grouped, list(grouped[0].keys()) if grouped else [])


def _prefix_cache_section(rows: Rows) -> str:
    if not rows:
        return "暂无 prefix-cache 数据。"
    table_rows: Rows = []
    for mode, group in _group_by(rows, ["mode"]).items():
        hashes = {str(row.get("stable_prefix_hash", "")) for row in group if row.get("stable_prefix_hash")}
        table_rows.append(
            {
                "mode": mode[0],
                "unique_prefix_hashes": len(hashes),
                "stable_prefix_tokens": _mean(group, "stable_prefix_tokens"),
                "prompt_tokens": _mean(group, "prompt_tokens"),
                "latency": _mean(group, "latency"),
                "ttft": _mean(group, "ttft"),
                "success_rate": _success_rate(group),
                "avg_score": _mean(group, "score"),
                "prefix_cache_hit_rate": _mean_available(group, "prefix_cache_hit_rate"),
                "cached_prompt_tokens": _mean_available(group, "cached_prompt_tokens"),
                "kv_cache_usage": _mean_available(group, "kv_cache_usage"),
            }
        )
    return _markdown_table(table_rows, list(table_rows[0].keys()))


def _ablation_section(rows: Rows) -> str:
    if not rows:
        return "暂无 ablation 数据。"
    columns = [
        "variant",
        "prompt_tokens",
        "latency",
        "raw_tool_tokens",
        "injected_tool_tokens",
        "tool_compression_ratio",
        "history_tokens",
        "summary_tokens",
        "loaded_skill_tokens",
        "unique_prefix_hashes",
        "prefix_reuse_score",
        "success",
        "score",
        "failure_reason",
    ]
    return _markdown_table(rows, columns)


def _agent_meta_section(frames: dict[str, Rows]) -> str:
    rows = [row for frame in frames.values() for row in frame if row.get("agent_meta_enabled") not in {None, ""}]
    if not rows:
        return "暂无 agent_meta 实验数据。"
    grouped = _group(rows, ["agent_meta_enabled", "scenario"], {
        "prompt_tokens": "mean",
        "latency": "mean",
        "ttft": "mean",
        "tokens_per_second": "mean",
        "cache_total_blocks": "max",
        "cache_agent_sessions": "max",
        "cache_tool_result_blocks": "max",
        "cache_shared_prefix_blocks": "max",
        "cache_scratchpad_blocks": "max",
        "cache_expired_branch_blocks": "max",
        "score": "mean",
    })
    for row in grouped:
        matching = [
            item
            for item in rows
            if str(item.get("agent_meta_enabled")) == str(row.get("agent_meta_enabled"))
            and item.get("scenario") == row.get("scenario")
        ]
        row["success_rate"] = _success_rate(matching)
    return _markdown_table(
        grouped,
        [
            "agent_meta_enabled",
            "scenario",
            "prompt_tokens",
            "latency",
            "ttft",
            "tokens_per_second",
            "cache_total_blocks",
            "cache_agent_sessions",
            "cache_tool_result_blocks",
            "cache_shared_prefix_blocks",
            "cache_scratchpad_blocks",
            "cache_expired_branch_blocks",
            "success_rate",
            "score",
        ],
    )


def _cache_pressure_section(rows: Rows) -> str:
    if not rows:
        return "暂无 cache-pressure 数据。"
    grouped = _group(rows, ["segment_type"], {
        "prompt_tokens": "mean",
        "latency": "mean",
        "ttft": "mean",
        "tokens_per_second": "mean",
        "cache_total_blocks": "max",
        "cache_agent_sessions": "max",
        "cache_tool_result_blocks": "max",
        "cache_shared_prefix_blocks": "max",
        "cache_scratchpad_blocks": "max",
        "cache_expired_branch_blocks": "max",
        "score": "mean",
    })
    for row in grouped:
        row["sessions"] = len({item.get("session_id") for item in rows if item.get("segment_type") == row.get("segment_type")})
        row["success_rate"] = _success_rate([item for item in rows if item.get("segment_type") == row.get("segment_type")])
    return _markdown_table(
        grouped,
        [
            "segment_type",
            "sessions",
            "prompt_tokens",
            "latency",
            "ttft",
            "tokens_per_second",
            "cache_total_blocks",
            "cache_agent_sessions",
            "cache_tool_result_blocks",
            "cache_shared_prefix_blocks",
            "cache_scratchpad_blocks",
            "cache_expired_branch_blocks",
            "success_rate",
            "score",
        ],
    )


def _ttl_priority_section(rows: Rows) -> str:
    if not rows:
        return "暂无 ttl-priority 数据。"
    grouped = _group(rows, ["segment_type", "priority", "ttl"], {
        "prompt_tokens": "mean",
        "latency": "mean",
        "ttft": "mean",
        "cache_total_blocks": "max",
        "cache_tool_result_blocks": "max",
        "cache_shared_prefix_blocks": "max",
        "cache_scratchpad_blocks": "max",
        "cache_expired_branch_blocks": "max",
        "score": "mean",
    })
    for row in grouped:
        row["success_rate"] = _success_rate(
            [
                item
                for item in rows
                if item.get("segment_type") == row.get("segment_type")
                and item.get("priority") == row.get("priority")
                and str(item.get("ttl")) == str(row.get("ttl"))
            ]
        )
    return _markdown_table(
        grouped,
        [
            "segment_type",
            "priority",
            "ttl",
            "prompt_tokens",
            "latency",
            "ttft",
            "cache_total_blocks",
            "cache_tool_result_blocks",
            "cache_shared_prefix_blocks",
            "cache_scratchpad_blocks",
            "cache_expired_branch_blocks",
            "success_rate",
            "score",
        ],
    )


def _cache_stats_availability_section(frames: dict[str, Rows]) -> str:
    rows = [row for frame in frames.values() for row in frame]
    if not rows:
        return "暂无 cache_stats 数据。"
    grouped = _group(rows, ["scenario", "cache_stats_available", "cache_stats_unavailable_reason"], {
        "cache_total_blocks": "max",
        "cache_agent_sessions": "max",
        "cache_tool_result_blocks": "max",
        "cache_shared_prefix_blocks": "max",
        "cache_scratchpad_blocks": "max",
        "cache_expired_branch_blocks": "max",
    })
    for row in grouped:
        row["rows"] = len(
            [
                item
                for item in rows
                if item.get("scenario") == row.get("scenario")
                and str(item.get("cache_stats_available")) == str(row.get("cache_stats_available"))
                and str(item.get("cache_stats_unavailable_reason")) == str(row.get("cache_stats_unavailable_reason"))
            ]
        )
    return _markdown_table(
        grouped,
        [
            "scenario",
            "cache_stats_available",
            "cache_stats_unavailable_reason",
            "rows",
            "cache_total_blocks",
            "cache_agent_sessions",
            "cache_tool_result_blocks",
            "cache_shared_prefix_blocks",
            "cache_scratchpad_blocks",
            "cache_expired_branch_blocks",
        ],
    )


def _cache_stats_scope_section(frames: dict[str, Rows]) -> str:
    rows = [row for frame in frames.values() for row in frame]
    available = any(_to_bool(row.get("cache_stats_available")) for row in rows)
    scope = "global cache view" if available else "unavailable"
    return "\n".join(
        [
            f"- cache_stats_scope: {scope}. 当前 `/v1/agentmem/cache_stats` 采集的是服务端全局 cache 视图；若服务端未来支持 by_agent/by_session 过滤，可用 summary.csv 中记录的 agent_id 过滤本次实验。",
            "- off 结果中如出现 expired_branch/tool_result/shared_prefix blocks，含义是全局历史缓存中已有这些 segment 的 block；off 请求本身没有携带 agent_meta，具体以 agent_meta_sent 和 audit_agent_meta.py 审计结果为准。",
        ]
    )


def _agent_meta_audit_section(frames: dict[str, Rows]) -> str:
    rows = [row for frame in frames.values() for row in frame if "agent_meta_sent" in row]
    if not rows:
        return "暂无可审计的 agent_meta 行。"
    grouped: Rows = []
    for key, group in _group_by(rows, ["agent_meta_enabled"]).items():
        sent_true = sum(1 for row in group if _to_bool(row.get("agent_meta_sent")))
        sent_false = len(group) - sent_true
        segment_counts: dict[str, int] = {}
        for row in group:
            segment = str(row.get("agent_meta_segment_type") or "")
            segment_counts[segment] = segment_counts.get(segment, 0) + 1
        grouped.append(
            {
                "agent_meta_enabled": key[0],
                "rows": len(group),
                "agent_meta_sent_true": sent_true,
                "agent_meta_sent_false": sent_false,
                "empty_segment_rows": segment_counts.get("", 0),
                "segment_type_distribution": "; ".join(
                    f"{segment or '<empty>'}:{count}" for segment, count in sorted(segment_counts.items())
                ),
            }
        )
    return _markdown_table(
        grouped,
        [
            "agent_meta_enabled",
            "rows",
            "agent_meta_sent_true",
            "agent_meta_sent_false",
            "empty_segment_rows",
            "segment_type_distribution",
        ],
    )


def _agent_meta_mapping_section() -> str:
    rows = [
        {"segment_type": "system", "agent_meta_usage": "系统指令和稳定角色约束", "priority": "high", "cache_behavior": "跨轮保留"},
        {"segment_type": "tool_schema", "agent_meta_usage": "工具说明、工具参数协议和调用边界", "priority": "high", "cache_behavior": "跨请求复用"},
        {"segment_type": "shared_prefix", "agent_meta_usage": "稳定 prefix、分支基座和公共项目规则", "priority": "high", "cache_behavior": "优先保留"},
        {"segment_type": "tool_result", "agent_meta_usage": "工具摘要、artifact ref 和大型结果索引", "priority": "normal/low", "cache_behavior": "显存压力下按优先级管理"},
        {"segment_type": "scratchpad", "agent_meta_usage": "planning/reflection 中间状态", "priority": "low", "cache_behavior": "短生命周期管理"},
        {"segment_type": "expired_branch", "agent_meta_usage": "过期分支和被替代候选路径", "priority": "drop", "cache_behavior": "优先释放"},
    ]
    return _markdown_table(rows, ["segment_type", "agent_meta_usage", "priority", "cache_behavior"])


def _conclusion(frames: dict[str, Rows]) -> str:
    reductions: list[tuple[str, float]] = []
    for name in ["tool_heavy", "long_session", "multi_stage", "prefix_cache"]:
        reduction = _mode_reduction(frames[name], "prompt_tokens")
        if reduction is not None:
            reductions.append((name, reduction))
    biggest = max(reductions, key=lambda item: item[1]) if reductions else ("暂无", 0.0)

    tool_rows = frames["tool_heavy"]
    max_tool_tokens = _max(tool_rows, "raw_tool_tokens") if tool_rows else 0

    best_variant = "暂无"
    ablation = frames["ablation"]
    if ablation:
        best_row = min(ablation, key=lambda row: _to_float(row.get("prompt_tokens")))
        best_variant = str(best_row.get("variant", ""))

    prefix_rows = frames["prefix_cache"]
    has_vllm_metrics = any(
        _to_float(row.get(column), -1) >= 0
        for row in prefix_rows
        for column in ["prefix_cache_hit_rate", "cached_prompt_tokens", "kv_cache_usage"]
    )
    has_cache_stats = any(
        _to_bool(row.get("cache_stats_available"))
        for rows in frames.values()
        for row in rows
    )
    scored_rows = [row for rows in frames.values() for row in rows if row.get("score") not in {None, ""}]
    overall_success = _success_rate(scored_rows) if scored_rows else 0.0

    lines = [
        f"- Token 降低最明显的场景：{biggest[0]}，prompt token reduction 约 {biggest[1]:.2f}%。",
        f"- 工具上下文膨胀来源：tool-heavy 场景最大 raw_tool_tokens 为 {max_tool_tokens:.0f}。",
        f"- 当前报告聚合任务成功率：{overall_success:.2f}%。",
        f"- Ablation 中 prompt_tokens 最低的配置：{best_variant}。",
        "- 真实 vLLM prefix 指标：已读取到兼容指标。" if has_vllm_metrics else "- 真实 vLLM prefix 指标：当前结果未包含可用兼容指标，相关字段保持 -1。",
        "- Agent-aware cache_stats：已读取到 /v1/agentmem/cache_stats。" if has_cache_stats else "- Agent-aware cache_stats：当前不可用或未返回目标字段，相关字段保持 -1。",
        "- Agent-aware 实验通过 agent_meta 将 session、context、segment、priority 和 ttl 显式传递给 vLLM 服务端，支持长生命周期、多工具、多 session 的 cache 管理观测。",
    ]
    return "\n".join(lines)


def _concat_existing(results: Path, names: list[str]) -> Rows:
    rows: Rows = []
    for name in names:
        rows.extend(_read_csv(results / name))
    return rows


def _read_csv(path: Path) -> Rows:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _write_csv(path: Path, rows: Rows, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _group(rows: Rows, by: list[str], agg: dict[str, str]) -> Rows:
    grouped_rows: Rows = []
    for key, group in _group_by(rows, by).items():
        row = {field: key[idx] for idx, field in enumerate(by)}
        for column, func in agg.items():
            row[column] = _max(group, column) if func == "max" else _mean(group, column)
        grouped_rows.append(row)
    return grouped_rows


def _group_by(rows: Rows, by: list[str]) -> dict[tuple[str, ...], Rows]:
    groups: dict[tuple[str, ...], Rows] = {}
    for row in rows:
        key = tuple(str(row.get(field, "")) for field in by)
        groups.setdefault(key, []).append(row)
    return groups


def _first_value(rows: Rows, column: str, default: Any) -> Any:
    for row in rows:
        value = row.get(column)
        if value not in {None, ""}:
            return value
    return default


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _mode_from_filename(name: str) -> str:
    if "baseline" in name:
        return "baseline"
    if "optimized" in name:
        return "optimized"
    return ""


def _detect_backend(frames: dict[str, Rows], default: str) -> str:
    for rows in frames.values():
        for row in rows:
            if row.get("backend"):
                return str(row["backend"])
    return default


def _mean(rows: Rows, column: str) -> float:
    values = [_to_float(row.get(column), None) for row in rows]
    numeric = [value for value in values if value is not None]
    return sum(numeric) / len(numeric) if numeric else 0.0


def _mean_available(rows: Rows, column: str) -> float:
    values = [_to_float(row.get(column), None) for row in rows]
    numeric = [value for value in values if value is not None and value >= 0]
    return sum(numeric) / len(numeric) if numeric else -1.0


def _success_rate(rows: Rows) -> float:
    values = [_to_bool(row.get("success")) for row in rows if row.get("success") not in {None, ""}]
    if not values:
        return 0.0
    return sum(1 for value in values if value) / len(values) * 100


def _max(rows: Rows, column: str) -> float:
    values = [_to_float(row.get(column), None) for row in rows]
    numeric = [value for value in values if value is not None]
    return max(numeric) if numeric else -1.0


def _first_numeric(rows: Rows, column: str) -> float:
    for row in rows:
        value = _to_float(row.get(column), None)
        if value is not None:
            return value
    return 0.0


def _last_numeric(rows: Rows, column: str, default: float = -1.0) -> float:
    for row in reversed(rows):
        value = _to_float(row.get(column), None)
        if value is not None:
            return value
    return default


def _round_value(rows: Rows, round_index: int, column: str) -> float:
    for row in rows:
        if int(_to_float(row.get("round"), -1)) == round_index:
            return _to_float(row.get(column), 0.0)
    return 0.0


def _last_rounds(rows: Rows) -> Rows:
    selected: Rows = []
    for _, group in _group_by(rows, ["mode"]).items():
        max_round = max((_to_float(row.get("round"), -1) for row in group), default=-1)
        selected.extend(row for row in group if _to_float(row.get("round"), -2) == max_round)
    return selected


def _mode_reduction(rows: Rows, column: str) -> float | None:
    if not rows:
        return None
    means = {key[0]: _mean(group, column) for key, group in _group_by(rows, ["mode"]).items()}
    if "baseline" not in means or "optimized" not in means:
        return None
    baseline = means["baseline"]
    optimized = means["optimized"]
    if baseline <= 0:
        return None
    return (baseline - optimized) / baseline * 100


def _mode_reduction_between(rows: Rows, baseline_mode: str, optimized_mode: str, column: str) -> float | None:
    means = {key[0]: _mean(group, column) for key, group in _group_by(rows, ["mode"]).items()}
    if baseline_mode not in means or optimized_mode not in means:
        return None
    baseline = means[baseline_mode]
    optimized = means[optimized_mode]
    if baseline <= 0:
        return None
    return (baseline - optimized) / baseline * 100


def _mode_delta(rows: Rows, baseline_mode: str, target_mode: str, column: str) -> float | None:
    means = {key[0]: _mean(group, column) for key, group in _group_by(rows, ["mode"]).items()}
    if baseline_mode not in means or target_mode not in means:
        return None
    return means[target_mode] - means[baseline_mode]


def _markdown_table(rows: Rows, columns: list[str]) -> str:
    if not rows or not columns:
        return "暂无数据。"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    output = [header, sep]
    for row in rows:
        output.append("| " + " | ".join(_format_cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join(output)


def _format_cell(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _to_float(value: Any, default: float | None = 0.0) -> float | None:
    if value in {None, ""}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
