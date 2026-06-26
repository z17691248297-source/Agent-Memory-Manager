from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from agentmem.metrics.hardware import collect_hardware_info
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
            }
        )
    return rows


def _build_report(config: dict[str, Any], frames: dict[str, Rows]) -> str:
    llm = dict(config.get("llm") or {})
    memory = dict(config.get("memory") or {})
    benchmark = dict(config.get("benchmark") or {})
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

    parts = [
        "# AgentMem Benchmark Report",
        "",
        "## 1. 项目目标",
        "",
        "AgentMem 是通用轻量 Agent Runtime + Memory Manager，用于让 Agent 通过 memory_delta 主动维护结构化任务状态，并通过 artifact_refs 管理工具结果。Benchmark 只用于评估不同任务场景下的上下文、质量和可追溯性表现；Memory 核心不依赖具体 benchmark 关键词。",
        "",
        "## 2. 实验设置",
        "",
        _settings_table(backend, llm, memory, benchmark, scenarios, modes),
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
        "## Mock Backend Results",
        "",
        _backend_results_section(frames, "mock"),
        "",
        "## vLLM Backend Results",
        "",
        _backend_results_section(frames, "vllm"),
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
        "该场景复现分支推理中公共上下文重复复制的问题。这里实现的是 Agent 上下文层共享，不是 vLLM 底层 KV block sharing。",
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
        "## 13. 当前局限性",
        "",
        _limitations_section(),
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
    memory: dict[str, Any],
    benchmark: dict[str, Any],
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
    rows = [
        {"item": "backend", "value": backend},
        {"item": "model", "value": _display_model(backend, llm)},
        {"item": "scenarios", "value": ", ".join(scenarios) if scenarios else "none"},
        {"item": "mode", "value": ", ".join(modes) if modes else "none"},
        {"item": "repeat", "value": benchmark.get("repeat", "")},
        {"item": "recent_rounds", "value": memory.get("recent_rounds", "")},
        {"item": "enabled_optimizations", "value": ", ".join(optimizations)},
    ]
    return _markdown_table(rows, ["item", "value"])


def _display_model(backend: str, llm: dict[str, Any]) -> str:
    return str(llm.get("model", ""))


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
    return _markdown_table(rows, ["scenario", "workload_file", "tasks"])


def _architecture_section() -> str:
    return "\n".join(
        [
            "本项目不是完整 AutoGPT，也不是通用 Web Agent。本项目实现的是支持典型智能体工作流的轻量 Agent Runtime，并将 Event-Sourced Memory 作为 Agent 侧内存管理优化机制。",
            "",
            "- AgentRuntime：负责多轮输入、轻量 next_action loop、工具执行、LLM 调用和指标采集。",
            "- Event-Sourced Memory：记录 user_message、tool_call、tool_result、assistant_response、memory_delta、final_answer、metric 等事件。",
            "- memory_delta：Agent 在同一次模型响应中主动写入 goals、constraints、facts、decisions、open_questions、todos、artifact_refs、tool_summaries 和 warnings。",
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
        "score": "mean",
    })
    for row in grouped:
        group_rows = [item for item in rows if item.get("scenario") == row.get("scenario") and item.get("mode") == row.get("mode")]
        row["success_rate"] = _success_rate(group_rows)
    note = "说明：本节使用 configs/config.yaml 中配置的模型 backend；latency、TTFT、tokens_per_second 和显存字段用于真实性能分析。/metrics 不可用时 prefix cache 字段为 -1。"
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
        "success_rate",
        "score",
    ]
    return "\n\n".join([note, _markdown_table(grouped, fields)])


def _limitations_section() -> str:
    return "\n".join(
        [
            "- vLLM 指标依赖服务端版本和 /metrics 暴露情况；缺失时报告为 -1。",
            "- 当前 next_action loop 是轻量实现，覆盖工具调用和有限多步决策，不是完整 AutoGPT。",
            "- Event-Sourced Memory 依赖模型按协议输出 memory_delta；非法 JSON 会 fallback 为普通回答。",
            "- 本项目不修改 vLLM kernel，不声称实现底层 KV block sharing。",
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
        "方法说明：Event Log 记录 Agent 执行事件；模型在同一次响应中输出 memory_delta；Memory Manager 将 goals、constraints、facts、decisions、todos 和 artifact_refs 合并为 Task State View；Renderer 只渲染状态视图、artifact metadata 和最近上下文。",
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
    scored_rows = [row for rows in frames.values() for row in rows if row.get("score") not in {None, ""}]
    overall_success = _success_rate(scored_rows) if scored_rows else 0.0

    lines = [
        f"- Token 降低最明显的场景：{biggest[0]}，prompt token reduction 约 {biggest[1]:.2f}%。",
        f"- 工具上下文膨胀来源：tool-heavy 场景最大 raw_tool_tokens 为 {max_tool_tokens:.0f}。",
        f"- 当前报告聚合任务成功率：{overall_success:.2f}%。",
        f"- Ablation 中 prompt_tokens 最低的配置：{best_variant}。",
        "- 真实 vLLM 指标：已读取到 /metrics 指标。" if has_vllm_metrics else "- 真实 vLLM 指标：当前结果未包含可用 /metrics，相关字段保持 -1。",
        "- 当前局限性：AgentMem 优化的是 Agent 上下文构造与外置存储路径，尚未修改 vLLM CUDA kernel 或底层 KV block manager。",
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
        writer = csv.DictWriter(file, fieldnames=fieldnames)
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
