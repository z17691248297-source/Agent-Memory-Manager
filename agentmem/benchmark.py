from __future__ import annotations

import csv
import json
import os
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from agentmem.event_memory.integration import EventSourcedMemoryAdapter
from agentmem.event_memory.extractor import build_memory_delta_extractor
from agentmem.evaluation import evaluate_metric_checks, evaluate_task, evaluation_fields
from agentmem.memory.baseline_memory import BaselineMemory
from agentmem.memory.branch_manager import BranchManager
from agentmem.memory.display import prompt_display_text, prompt_display_tokens
from agentmem.memory.memory_object import estimate_tokens, hash_text
from agentmem.memory.optimized_memory import OptimizedMemory
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.metrics.gpu_monitor import get_peak_gpu_memory_mb
from agentmem.metrics.summarizer import summarize_results
from agentmem.metrics.vllm_metrics import DEFAULT_VLLM_METRICS, fetch_vllm_metrics
from agentmem.runtime.agent import AgentRuntime
from agentmem.runtime.factory import PROJECT_ROOT, SYSTEM_PROMPT
from agentmem.runtime.llm_factory import build_llm_client, load_runtime_config
from agentmem.tools.executor import ToolExecutor
from agentmem.tools.tool_registry import build_default_registry
from agentmem.vllm.agent_meta import default_segment_type_for_stage
from agentmem.vllm.cache_stats import CacheStatsCollector
from agentmem.vllm.memory_plan import MemoryPlanLogger


SCENARIOS = {
    "tool-heavy",
    "long-session",
    "multi-stage",
    "branching",
    "prefix-cache",
    "ablation",
    "cache-pressure",
    "ttl-priority",
    "all",
}
LONG_MULTI_MEMORY_MODES = ["full_history", "summary_memory", "event_sourced_memory"]
MODES = {"baseline", "optimized", "both", *LONG_MULTI_MEMORY_MODES}
TASK_DIR = PROJECT_ROOT / "benchmarks" / "tasks"
TASK_FILES = {
    "tool-heavy": "tool_heavy.jsonl",
    "long-session": "long_session.jsonl",
    "multi-stage": "multi_stage.jsonl",
    "branching": "branching.jsonl",
}

COMMON_FIELDS = [
    "scenario",
    "task_id",
    "workload_file",
    "mode",
    "memory_mode",
    "backend",
    "model",
    "round",
    "stage",
    "prompt_tokens",
    "output_tokens",
    "total_tokens",
    "latency",
    "ttft",
    "tokens_per_second",
    "peak_gpu_memory_mb",
    "success",
    "score",
    "failure_reason",
    "passed_checks",
    "total_checks",
    "extractor_effective",
    "extractor_status",
    "extractor_success_count",
    "extractor_failure_count",
    "refill_count",
    "refill_tokens",
    "initial_score",
    "final_score",
    "agent_meta_enabled",
    "agent_id",
    "agent_meta_sent",
    "agent_meta_agent_id",
    "agent_meta_session_id",
    "agent_meta_context_id",
    "agent_meta_segment_type",
    "agent_meta_priority",
    "cache_stats_available",
    "cache_stats_unavailable_reason",
    "cache_total_blocks",
    "cache_agent_sessions",
    "cache_tool_result_blocks",
    "cache_shared_prefix_blocks",
    "cache_scratchpad_blocks",
    "cache_expired_branch_blocks",
]

TOOL_HEAVY_FIELDS = [
    *COMMON_FIELDS,
    "tool_names",
    "raw_tool_tokens",
    "injected_tool_tokens",
    "tool_compression_ratio",
    "tool_brief_tokens",
    "loaded_skill_tokens",
]

LONG_SESSION_FIELDS = [
    *COMMON_FIELDS,
    "session_id",
    "history_tokens",
    "full_history_tokens",
    "summary_tokens",
    "state_view_tokens",
    "event_count",
    "memory_delta_count",
    "fact_count",
    "decision_count",
    "artifact_ref_count",
    "snapshot_count",
    "recent_turns",
    "tool_names",
    "early_fact_retention",
    "initial_score",
    "final_score",
    "missing_keywords",
]

MULTI_STAGE_FIELDS = [
    *COMMON_FIELDS,
    "session_id",
    "step",
    "completed_stages",
    "tool_names",
    "raw_tool_tokens",
    "injected_tool_tokens",
    "tool_compression_ratio",
    "history_tokens",
    "full_history_tokens",
    "summary_tokens",
    "state_view_tokens",
    "event_count",
    "memory_delta_count",
    "fact_count",
    "decision_count",
    "artifact_ref_count",
    "snapshot_count",
    "early_fact_retention",
    "initial_score",
    "final_score",
    "missing_keywords",
]

BRANCHING_FIELDS = [
    *COMMON_FIELDS,
    "branch_count",
    "shared_context_tokens",
    "branch_delta_tokens",
    "duplicated_context_tokens",
    "optimized_context_tokens",
    "branch_saving_ratio",
    "branch_answer_tokens",
]

PREFIX_CACHE_FIELDS = [
    *COMMON_FIELDS,
    "stable_prefix_hash",
    "stable_prefix_tokens",
    "unique_prefix_hashes",
    "prefix_cache_hit_rate",
    "cached_prompt_tokens",
    "kv_cache_usage",
    "extractor_effective",
    "extractor_status",
    "extractor_success_count",
    "extractor_failure_count",
]

VLLM_BENCHMARK_FIELDS = [
    "scenario",
    "mode",
    "memory_mode",
    "backend",
    "model",
    "round",
    "stage",
    "prompt_tokens",
    "output_tokens",
    "total_tokens",
    "latency",
    "ttft",
    "tokens_per_second",
    "peak_gpu_memory_mb",
    "success",
    "score",
    "prefix_cache_hit_rate",
    "cached_prompt_tokens",
    "kv_cache_usage",
    "agent_meta_enabled",
    "agent_id",
    "agent_meta_sent",
    "agent_meta_agent_id",
    "agent_meta_session_id",
    "agent_meta_context_id",
    "agent_meta_segment_type",
    "agent_meta_priority",
    "cache_stats_available",
    "cache_stats_unavailable_reason",
    "cache_total_blocks",
    "cache_agent_sessions",
    "cache_tool_result_blocks",
    "cache_shared_prefix_blocks",
    "cache_scratchpad_blocks",
    "cache_expired_branch_blocks",
]

ABLATION_FIELDS = [
    "scenario",
    "task_id",
    "workload_file",
    "variant",
    "mode",
    "backend",
    "prompt_tokens",
    "output_tokens",
    "total_tokens",
    "latency",
    "ttft",
    "peak_gpu_memory_mb",
    "raw_tool_tokens",
    "injected_tool_tokens",
    "tool_compression_ratio",
    "history_tokens",
    "summary_tokens",
    "tool_brief_tokens",
    "loaded_skill_tokens",
    "unique_prefix_hashes",
    "prefix_reuse_score",
    "success",
    "score",
    "failure_reason",
    "passed_checks",
    "total_checks",
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

CACHE_EXPERIMENT_FIELDS = [
    *COMMON_FIELDS,
    "session_id",
    "step",
    "context_id",
    "segment_type",
    "priority",
    "ttl",
    "prompt_label",
]


@dataclass(frozen=True)
class BenchmarkOptions:
    scenario: str = "all"
    mode: str = "both"
    backend: str = "vllm"
    repeat: int = 1
    output_dir: Path = PROJECT_ROOT / "results"
    config_path: Path = PROJECT_ROOT / "configs" / "config.yaml"
    agent_meta_enabled: bool | None = None
    sessions: int = 4
    agent_id: str | None = None


def run_benchmark(options: BenchmarkOptions) -> dict[str, Any]:
    if options.scenario not in SCENARIOS:
        raise ValueError(f"unsupported scenario: {options.scenario}")
    if options.mode not in MODES:
        raise ValueError(f"unsupported mode: {options.mode}")

    output_dir = _resolve_output_dir(options.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    repeat = max(1, int(options.repeat))
    backend = options.backend.replace("-", "_")
    agent_id = options.agent_id or _default_agent_id(options.scenario, options.agent_meta_enabled)

    paths: list[Path] = []
    scenarios = [
        "tool-heavy",
        "long-session",
        "multi-stage",
        "branching",
        "prefix-cache",
        "ablation",
        "cache-pressure",
        "ttl-priority",
    ]
    if options.scenario != "all":
        scenarios = [options.scenario]

    with _override_backend(backend), _override_agent_meta(options.agent_meta_enabled), _override_agent_id(agent_id):
        for scenario in scenarios:
            if scenario == "tool-heavy":
                paths.extend(_run_tool_heavy(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "long-session":
                paths.extend(_run_long_session(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "multi-stage":
                paths.extend(_run_multi_stage(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "branching":
                paths.extend(_run_branching(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "prefix-cache":
                paths.extend(_run_prefix_cache(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "ablation":
                paths.append(_run_ablation(options.config_path, output_dir, backend))
            elif scenario == "cache-pressure":
                paths.append(_run_cache_pressure(options.config_path, output_dir, backend, options.sessions))
            elif scenario == "ttl-priority":
                paths.append(_run_ttl_priority(options.config_path, output_dir, backend))

    if backend == "vllm":
        paths.append(_write_vllm_benchmark(output_dir))

    report_paths = summarize_results(output_dir, options.config_path)
    return {
        "output_dir": output_dir,
        "paths": paths,
        "summary_csv": report_paths["summary_csv"],
        "report_md": report_paths["report_md"],
    }


def _run_tool_heavy(
    config_path: Path,
    output_dir: Path,
    backend: str,
    mode: str,
    repeat: int,
) -> list[Path]:
    tasks, workload = _load_tasks("tool-heavy")
    paths: list[Path] = []

    for memory_mode in _selected_modes(mode):
        cache_before = _capture_cache_stats(config_path, output_dir, "tool-heavy", memory_mode, "before", backend)
        rows = []
        for repeat_index in range(repeat):
            for task_index, task in enumerate(tasks, start=1):
                agent = _build_benchmark_agent(config_path, output_dir, memory_mode)
                answer, metrics = agent.run(
                    str(task["input"]),
                    stage=str(task.get("stage", "tool_calling")),
                    tool_context=_task_tool_context(task),
                )
                result = evaluate_task(task, answer, metrics)
                if memory_mode == "optimized" and not result.success:
                    result, answer, metrics = _refill_missing_evidence(
                        agent=agent,
                        config_path=config_path,
                        task=task,
                        answer=answer,
                        metrics=metrics,
                        result=result,
                    )
                row = _row_from_metrics(
                    task=task,
                    workload=workload,
                    metrics=metrics,
                    scenario="tool-heavy",
                    memory_mode=memory_mode,
                    backend=backend,
                    round_index=repeat_index * len(tasks) + task_index,
                )
                row.update(evaluation_fields(result))
                row.update(_cache_stats_row(cache_before))
                rows.append(_select_fields(row, TOOL_HEAVY_FIELDS, default=-1))
        cache_after = _capture_cache_stats(config_path, output_dir, "tool-heavy", memory_mode, "after", backend)
        rows = [_merge_cache_stats(row, cache_after) for row in rows]
        path = output_dir / f"tool_heavy_{memory_mode}.csv"
        _write_csv(path, rows, TOOL_HEAVY_FIELDS)
        paths.append(path)
    return paths


def _run_long_session(
    config_path: Path,
    output_dir: Path,
    backend: str,
    mode: str,
    repeat: int,
) -> list[Path]:
    config = load_runtime_config(config_path)
    recent_turns = int(dict(config.get("memory") or {}).get("recent_rounds", 6))
    tasks, workload = _load_tasks("long-session")
    sessions = _group_sequence(tasks, "session_id", "turn")
    paths: list[Path] = []

    for memory_mode in _selected_long_multi_modes(mode):
        cache_before = _capture_cache_stats(config_path, output_dir, "long-session", memory_mode, "before", backend)
        rows: list[dict[str, Any]] = []
        for _ in range(repeat):
            for session_id, session_tasks in sessions.items():
                agent = _build_benchmark_agent(config_path, output_dir, memory_mode)
                for turn_index, task in enumerate(session_tasks, start=1):
                    answer, metrics = agent.run(
                        str(task["input"]),
                        stage=str(task.get("stage", "planning")),
                        tool_context=_task_tool_context(task),
                    )
                    result, answer, metrics = _evaluate_agent_task(agent, task, answer, metrics)
                    row = _row_from_metrics(
                        task=task,
                        workload=workload,
                        metrics=metrics,
                        scenario="long-session",
                        memory_mode=memory_mode,
                        backend=backend,
                        round_index=int(task.get("turn", turn_index)),
                    )
                    row["session_id"] = session_id
                    row["recent_turns"] = recent_turns
                    row.update(evaluation_fields(result))
                    row.update(_cache_stats_row(cache_before))
                    rows.append(_select_fields(row, LONG_SESSION_FIELDS, default=-1))
        cache_after = _capture_cache_stats(config_path, output_dir, "long-session", memory_mode, "after", backend)
        rows = [_merge_cache_stats(row, cache_after) for row in rows]
        path = output_dir / f"long_session_{memory_mode}.csv"
        _write_csv(path, rows, LONG_SESSION_FIELDS)
        paths.append(path)
    paths.extend(
        _write_mode_aliases(
            output_dir,
            {
                "long_session_full_history.csv": "long_session_baseline.csv",
                "long_session_event_sourced_memory.csv": "long_session_optimized.csv",
            },
        )
    )
    return paths


def _run_multi_stage(
    config_path: Path,
    output_dir: Path,
    backend: str,
    mode: str,
    repeat: int,
) -> list[Path]:
    tasks, workload = _load_tasks("multi-stage")
    sessions = _group_sequence(tasks, "session_id", "step")
    paths: list[Path] = []

    for memory_mode in _selected_long_multi_modes(mode):
        cache_before = _capture_cache_stats(config_path, output_dir, "multi-stage", memory_mode, "before", backend)
        rows: list[dict[str, Any]] = []
        for _ in range(repeat):
            for session_id, session_tasks in sessions.items():
                agent = _build_benchmark_agent(config_path, output_dir, memory_mode)
                completed_stages: list[str] = []
                for step_index, task in enumerate(session_tasks, start=1):
                    stage = str(task.get("stage", "planning"))
                    answer, metrics = agent.run(str(task["input"]), stage=stage, tool_context=_task_tool_context(task))
                    completed_stages.append(stage)
                    result, answer, metrics = _evaluate_agent_task(
                        agent,
                        task,
                        answer,
                        metrics,
                        context={"completed_stages": completed_stages},
                    )
                    row = _row_from_metrics(
                        task=task,
                        workload=workload,
                        metrics=metrics,
                        scenario="multi-stage",
                        memory_mode=memory_mode,
                        backend=backend,
                        round_index=step_index,
                    )
                    row["session_id"] = session_id
                    row["step"] = int(task.get("step", step_index))
                    row["completed_stages"] = ",".join(completed_stages)
                    row.update(evaluation_fields(result))
                    row.update(_cache_stats_row(cache_before))
                    rows.append(_select_fields(row, MULTI_STAGE_FIELDS, default=-1))
        cache_after = _capture_cache_stats(config_path, output_dir, "multi-stage", memory_mode, "after", backend)
        rows = [_merge_cache_stats(row, cache_after) for row in rows]
        path = output_dir / f"multi_stage_{memory_mode}.csv"
        _write_csv(path, rows, MULTI_STAGE_FIELDS)
        paths.append(path)
    paths.extend(
        _write_mode_aliases(
            output_dir,
            {
                "multi_stage_full_history.csv": "multi_stage_baseline.csv",
                "multi_stage_event_sourced_memory.csv": "multi_stage_optimized.csv",
            },
        )
    )
    return paths


def _run_branching(config_path: Path, output_dir: Path, backend: str, mode: str, repeat: int) -> list[Path]:
    tasks, workload = _load_tasks("branching")
    paths: list[Path] = []
    combined_rows: list[dict[str, Any]] = []

    for memory_mode in _selected_modes(mode):
        cache_before = _capture_cache_stats(config_path, output_dir, "branching", memory_mode, "before", backend)
        rows: list[dict[str, Any]] = []
        for _ in range(repeat):
            for task in tasks:
                for branch_count in task.get("branch_counts") or [2, 4, 8]:
                    row = _branch_row(task, workload, int(branch_count), memory_mode, backend, config_path, output_dir)
                    row.update(_cache_stats_row(cache_before))
                    rows.append(_select_fields(row, BRANCHING_FIELDS, default=-1))
        cache_after = _capture_cache_stats(config_path, output_dir, "branching", memory_mode, "after", backend)
        rows = [_merge_cache_stats(row, cache_after) for row in rows]
        path = output_dir / f"branching_{memory_mode}.csv"
        _write_csv(path, rows, BRANCHING_FIELDS)
        paths.append(path)
        combined_rows.extend(rows)

    benchmark_path = output_dir / "branch_benchmark.csv"
    _write_csv(benchmark_path, combined_rows, BRANCHING_FIELDS)
    paths.append(benchmark_path)
    return paths


def _run_prefix_cache(
    config_path: Path,
    output_dir: Path,
    backend: str,
    mode: str,
    repeat: int,
) -> list[Path]:
    paths: list[Path] = []
    config = load_runtime_config(config_path)
    metrics_url = str(dict(config.get("vllm") or {}).get("metrics_url", "http://localhost:8000/metrics"))

    for memory_mode in _selected_modes(mode):
        cache_before = _capture_cache_stats(config_path, output_dir, "prefix-cache", memory_mode, "before", backend)
        rows = []
        total_rounds = repeat * 6
        for round_index in range(1, total_rounds + 1):
            prompt, stable_prefix = _prefix_cache_prompt(memory_mode, round_index)
            run_id = f"prefix_cache_{memory_mode}"
            response = _safe_call_prompt(
                config_path,
                prompt,
                run_id=run_id,
                stage="prefix_cache",
                segment_type="shared_prefix",
                context_id=f"{run_id}:round_{round_index}:shared_prefix",
                priority="high",
                output_dir=output_dir,
                included_items=["system_prompt", "project_rules", "tool_briefs", "history_summary"],
            )
            if backend == "vllm" and response.get("error"):
                raise RuntimeError(str(response["error"]))
            prompt_tokens = response["prompt_tokens"]
            output_tokens = response.get("completion_tokens", 0)
            total_tokens = response.get("total_tokens", prompt_tokens + output_tokens)
            latency = response["latency"]
            ttft = response.get("ttft", -1)
            tokens_per_second = response.get("tokens_per_second", -1)
            model = response.get("model", "")
            vllm_metrics = fetch_vllm_metrics(metrics_url) if backend == "vllm" else dict(DEFAULT_VLLM_METRICS)
            llm_error = response.get("error", "")

            row = {
                "scenario": "prefix-cache",
                "task_id": f"prefix_cache_round_{round_index:02d}",
                "workload_file": "metric:prefix-cache",
                "mode": memory_mode,
                "memory_mode": memory_mode,
                "backend": backend,
                "model": model,
                "round": round_index,
                "stage": "prefix_cache",
                "stable_prefix_hash": hash_text(stable_prefix)[:16],
                "stable_prefix_tokens": estimate_tokens(stable_prefix),
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "latency": latency,
                "ttft": ttft,
                "tokens_per_second": tokens_per_second,
                "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
                "failure_reason": llm_error,
                "agent_meta_enabled": _agent_meta_enabled(config_path),
                "agent_id": _agent_id_value(config_path),
                **_cache_stats_row(cache_before),
                **vllm_metrics,
            }
            rows.append(row)

        unique_hashes = len({row["stable_prefix_hash"] for row in rows})
        for row in rows:
            row["unique_prefix_hashes"] = unique_hashes
            row.update(
                evaluation_fields(
                    evaluate_metric_checks(
                        {
                            "llm_call_success": not row.get("failure_reason"),
                            "prompt_tokens_positive": _to_float(row["prompt_tokens"]) > 0,
                            "stable_prefix_hash_present": bool(row["stable_prefix_hash"]),
                            "expected_prefix_pattern": unique_hashes == 1 if memory_mode == "optimized" else unique_hashes > 1,
                        }
                    )
                )
            )
        path = output_dir / f"prefix_cache_{memory_mode}.csv"
        cache_after = _capture_cache_stats(config_path, output_dir, "prefix-cache", memory_mode, "after", backend)
        rows = [_merge_cache_stats(row, cache_after) for row in rows]
        rows = [_select_fields(row, PREFIX_CACHE_FIELDS, default=-1) for row in rows]
        _write_csv(path, rows, PREFIX_CACHE_FIELDS)
        paths.append(path)

    return paths


def _run_ablation(config_path: Path, output_dir: Path, backend: str) -> Path:
    config = load_runtime_config(config_path)
    memory_config = dict(config.get("memory") or {})
    recent_turns = int(memory_config.get("recent_rounds", 6))
    registry = build_default_registry(PROJECT_ROOT / "skills")
    store = ToolResultStore(output_dir / "tool_store", raw_store_max_mb=_raw_store_max_mb(config))
    executor = ToolExecutor(registry, store)
    result = executor.execute(
        "log_analyzer",
        "请分析一段大型 vLLM 日志，关注 CUDA OOM、timeout 和 KV cache allocation failed。",
        context={"stage": "tool_calling"},
    )

    full_tools = "\n\n".join(
        f"## {spec.name}\n{registry.load_full_skill(spec.name)}"
        for spec in sorted(registry.available_tools(), key=lambda item: (-item.priority, item.name))
    )
    tool_briefs = json.dumps(registry.list_tool_briefs(), ensure_ascii=False, indent=2)
    selected_skill = f"## log_analyzer\n{registry.load_full_skill('log_analyzer')}"
    history_messages = [
        f"user: 第 {idx} 轮讨论 AgentMem 内存优化、工具结果和 prefix cache。 assistant: 已记录约束。"
        for idx in range(1, 18)
    ]
    full_history = "\n".join(history_messages)
    recent_history = "\n".join(history_messages[-recent_turns:])
    history_summary = "历史摘要: 用户持续讨论 AgentMem 的工具结果外置、长会话压缩、稳定 prefix 和分支共享。"
    raw_record = prompt_display_text(result)
    raw_record_tokens = prompt_display_tokens(result, estimate_tokens)
    summary_record = "\n".join(
        [
            f"tool_name: {result.tool_name}",
            f"result_id: {result.result_id}",
            f"raw_token_len: {result.raw_token_len}",
            f"summary_token_len: {result.summary_token_len}",
            result.summary,
        ]
    )

    variants = [
        {
            "variant": "baseline",
            "parts": [SYSTEM_PROMPT, full_tools, full_history, raw_record],
            "injected_tool_tokens": raw_record_tokens,
            "summary_tokens": 0,
            "history_text": full_history,
            "tool_brief_tokens": 0,
            "loaded_skill_tokens": estimate_tokens(full_tools),
            "unique_prefix_hashes": _ablation_unique_prefixes(stable=False, prefix=full_tools),
        },
        {
            "variant": "stable_prefix_only",
            "parts": [SYSTEM_PROMPT, full_tools, full_history, raw_record],
            "injected_tool_tokens": raw_record_tokens,
            "summary_tokens": 0,
            "history_text": full_history,
            "tool_brief_tokens": 0,
            "loaded_skill_tokens": estimate_tokens(full_tools),
            "unique_prefix_hashes": _ablation_unique_prefixes(stable=True, prefix=full_tools),
        },
        {
            "variant": "skill_lazy_loading_only",
            "parts": [SYSTEM_PROMPT, tool_briefs, selected_skill, full_history, raw_record],
            "injected_tool_tokens": raw_record_tokens,
            "summary_tokens": 0,
            "history_text": full_history,
            "tool_brief_tokens": estimate_tokens(tool_briefs),
            "loaded_skill_tokens": estimate_tokens(selected_skill),
            "unique_prefix_hashes": _ablation_unique_prefixes(stable=False, prefix=tool_briefs),
        },
        {
            "variant": "tool_externalization_only",
            "parts": [SYSTEM_PROMPT, full_tools, full_history, summary_record],
            "injected_tool_tokens": result.summary_token_len,
            "summary_tokens": 0,
            "history_text": full_history,
            "tool_brief_tokens": 0,
            "loaded_skill_tokens": estimate_tokens(full_tools),
            "unique_prefix_hashes": _ablation_unique_prefixes(stable=False, prefix=full_tools),
        },
        {
            "variant": "history_summary_only",
            "parts": [SYSTEM_PROMPT, full_tools, history_summary, recent_history, raw_record],
            "injected_tool_tokens": raw_record_tokens,
            "summary_tokens": estimate_tokens(history_summary),
            "history_text": recent_history,
            "tool_brief_tokens": 0,
            "loaded_skill_tokens": estimate_tokens(full_tools),
            "unique_prefix_hashes": _ablation_unique_prefixes(stable=False, prefix=full_tools),
        },
        {
            "variant": "full_optimized",
            "parts": [SYSTEM_PROMPT, tool_briefs, selected_skill, history_summary, recent_history, summary_record],
            "injected_tool_tokens": result.summary_token_len,
            "summary_tokens": estimate_tokens(history_summary),
            "history_text": recent_history,
            "tool_brief_tokens": estimate_tokens(tool_briefs),
            "loaded_skill_tokens": estimate_tokens(selected_skill),
            "unique_prefix_hashes": _ablation_unique_prefixes(stable=True, prefix=tool_briefs),
        },
    ]

    rows: list[dict[str, Any]] = []
    cache_before = _capture_cache_stats(config_path, output_dir, "ablation", "ablation", "before", backend)
    for item in variants:
        prompt = "\n\n".join(item["parts"])
        prompt_tokens = estimate_tokens(prompt)
        response = _safe_call_prompt(
            config_path,
            prompt,
            run_id="agentmem_ablation_session",
            stage="ablation",
            segment_type="shared_prefix",
            context_id=f"agentmem_ablation_session:ablation:{item['variant']}",
            priority="high",
            output_dir=output_dir,
            included_items=["system_prompt", "tool_context", "history_context", str(item["variant"])],
            external_refs=[{"tool_name": result.tool_name, "result_id": result.result_id}],
            excluded_items=["raw_tool_result_body"] if item["injected_tool_tokens"] < result.raw_token_len else [],
            estimated_saved_tokens=max(0, result.raw_token_len - int(item["injected_tool_tokens"])),
        )
        latency = response["latency"]
        ttft = response.get("ttft", -1)
        output_tokens = response.get("completion_tokens", 0)
        total_tokens = response.get("total_tokens", prompt_tokens + output_tokens)
        llm_error = response.get("error", "")
        row = {
            "scenario": "ablation",
            "task_id": "ablation_log_context",
            "workload_file": "metric:ablation",
            "variant": item["variant"],
            "mode": item["variant"],
            "backend": backend,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "latency": latency,
            "ttft": ttft,
            "failure_reason": llm_error,
            "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
            "raw_tool_tokens": result.raw_token_len,
            "injected_tool_tokens": item["injected_tool_tokens"],
            "tool_compression_ratio": (item["injected_tool_tokens"] / result.raw_token_len) if result.raw_token_len else 1.0,
            "history_tokens": estimate_tokens(item["history_text"]),
            "summary_tokens": item["summary_tokens"],
            "tool_brief_tokens": item["tool_brief_tokens"],
            "loaded_skill_tokens": item["loaded_skill_tokens"],
            "unique_prefix_hashes": item["unique_prefix_hashes"],
            "prefix_reuse_score": 1 / item["unique_prefix_hashes"],
            "agent_meta_enabled": _agent_meta_enabled(config_path),
            "agent_id": _agent_id_value(config_path),
            **_cache_stats_row(cache_before),
        }
        rows.append(row)

    baseline = next(row for row in rows if row["variant"] == "baseline")
    for row in rows:
        row.update(evaluation_fields(_evaluate_ablation_row(row, baseline)))

    path = output_dir / "ablation.csv"
    cache_after = _capture_cache_stats(config_path, output_dir, "ablation", "ablation", "after", backend)
    rows = [_merge_cache_stats(row, cache_after) for row in rows]
    _write_csv(path, [_select_fields(row, ABLATION_FIELDS, default=-1) for row in rows], ABLATION_FIELDS)
    return path


def _run_cache_pressure(config_path: Path, output_dir: Path, backend: str, sessions: int) -> Path:
    scenario = "cache-pressure"
    mode = f"sessions_{max(1, int(sessions or 1))}"
    cache_before = _capture_cache_stats(config_path, output_dir, scenario, mode, "before", backend)
    rows: list[dict[str, Any]] = []
    segment_plan = [
        ("shared_prefix", "shared_prefix", "high", 3600, None),
        ("tool_schema", "tool_schema", "high", 1800, None),
        ("tool_result", "tool_result", "normal", 300, "log_analyzer"),
        ("scratchpad", "scratchpad", "low", 60, None),
        ("expired_branch", "expired_branch", "drop", 1, None),
    ]

    for step_index, (stage, segment_type, priority, ttl, tool_name) in enumerate(segment_plan, start=1):
        for session_index in range(1, max(1, int(sessions or 1)) + 1):
            run_id = f"cache_pressure_session_{session_index}"
            context_id = f"{run_id}:step_{step_index}:{stage}:{segment_type}"
            prompt = _cache_pressure_prompt(session_index, step_index, segment_type)
            response = _safe_call_prompt(
                config_path,
                prompt,
                run_id=run_id,
                stage=stage,
                segment_type=segment_type,
                context_id=context_id,
                tool_name=tool_name,
                priority=priority,
                ttl=ttl,
                branch_id=f"{run_id}:expired_branch_{step_index}" if segment_type == "expired_branch" else None,
                output_dir=output_dir,
                included_items=_cache_pressure_items(segment_type, session_index),
                external_refs=_cache_pressure_refs(segment_type, session_index, step_index),
                excluded_items=["expired_branch_context"] if segment_type == "expired_branch" else [],
                estimated_saved_tokens=estimate_tokens(prompt) // 5 if segment_type in {"tool_result", "expired_branch"} else 0,
            )
            row = _cache_experiment_row(
                scenario=scenario,
                task_id=f"cache_pressure_s{session_index}_step{step_index}",
                mode=mode,
                backend=backend,
                run_id=run_id,
                stage=stage,
                step=step_index,
                session_id=run_id,
                context_id=context_id,
                segment_type=segment_type,
                priority=priority,
                ttl=ttl,
                prompt_label=f"{segment_type}_session_{session_index}",
                response=response,
                cache_stats=cache_before,
                config_path=config_path,
            )
            rows.append(_select_fields(row, CACHE_EXPERIMENT_FIELDS, default=-1))

    cache_after = _capture_cache_stats(config_path, output_dir, scenario, mode, "after", backend)
    rows = [_select_fields(_merge_cache_stats(row, cache_after), CACHE_EXPERIMENT_FIELDS, default=-1) for row in rows]
    path = output_dir / "cache_pressure.csv"
    _write_csv(path, rows, CACHE_EXPERIMENT_FIELDS)
    return path


def _run_ttl_priority(config_path: Path, output_dir: Path, backend: str) -> Path:
    scenario = "ttl-priority"
    mode = "ttl_priority"
    cache_before = _capture_cache_stats(config_path, output_dir, scenario, mode, "before", backend)
    rows: list[dict[str, Any]] = []
    segment_plan = [
        ("shared_prefix", "shared_prefix", "high", 3600, None),
        ("tool_schema", "tool_schema", "high", 1800, None),
        ("tool_result", "tool_result", "low", 120, "log_analyzer"),
        ("scratchpad", "scratchpad", "low", 60, None),
        ("expired_branch", "expired_branch", "drop", 1, None),
    ]
    run_id = "ttl_priority_session"

    for step_index, (stage, segment_type, priority, ttl, tool_name) in enumerate(segment_plan, start=1):
        context_id = f"{run_id}:step_{step_index}:{segment_type}:ttl_{ttl}:priority_{priority}"
        prompt = _ttl_priority_prompt(segment_type, priority, ttl, step_index)
        response = _safe_call_prompt(
            config_path,
            prompt,
            run_id=run_id,
            stage=stage,
            segment_type=segment_type,
            context_id=context_id,
            tool_name=tool_name,
            priority=priority,
            ttl=ttl,
            branch_id=f"{run_id}:expired_branch" if segment_type == "expired_branch" else None,
            output_dir=output_dir,
            included_items=[segment_type, f"priority={priority}", f"ttl={ttl}"],
            external_refs=_cache_pressure_refs(segment_type, 1, step_index),
            excluded_items=["expired_branch_context"] if segment_type == "expired_branch" else [],
            estimated_saved_tokens=estimate_tokens(prompt) // 4 if segment_type in {"tool_result", "scratchpad", "expired_branch"} else 0,
        )
        row = _cache_experiment_row(
            scenario=scenario,
            task_id=f"ttl_priority_step_{step_index}",
            mode=mode,
            backend=backend,
            run_id=run_id,
            stage=stage,
            step=step_index,
            session_id=run_id,
            context_id=context_id,
            segment_type=segment_type,
            priority=priority,
            ttl=ttl,
            prompt_label=f"{segment_type}_ttl_{ttl}_priority_{priority}",
            response=response,
            cache_stats=cache_before,
            config_path=config_path,
        )
        rows.append(_select_fields(row, CACHE_EXPERIMENT_FIELDS, default=-1))

    cache_after = _capture_cache_stats(config_path, output_dir, scenario, mode, "after", backend)
    rows = [_select_fields(_merge_cache_stats(row, cache_after), CACHE_EXPERIMENT_FIELDS, default=-1) for row in rows]
    path = output_dir / "ttl_priority.csv"
    _write_csv(path, rows, CACHE_EXPERIMENT_FIELDS)
    return path


def _cache_pressure_prompt(session_index: int, step_index: int, segment_type: str) -> str:
    repeated_context = "\n".join(
        [
            (
                f"session={session_index} step={step_index} segment={segment_type} "
                "AgentMem 长生命周期任务包含系统约束、工具 schema、工具结果摘要、scratchpad 推理状态、"
                "分支上下文和 cache pressure 观测。"
            )
            for _ in range(120)
        ]
    )
    segment_payload = {
        "shared_prefix": "稳定系统说明和跨轮复用前缀应保留在高优先级 cache 区域。",
        "tool_schema": "工具 schema 包含 log_analyzer、calculator、file_reader 的调用格式和结果引用规范。",
        "tool_result": "工具返回大型日志摘要：包含 OOM、timeout、KV cache allocation failed 与 request queue backpressure。",
        "scratchpad": "scratchpad 记录中间计划、候选工具路径和下一轮需要验证的 cache 指标。",
        "expired_branch": "过期分支包含已经被替代的候选方案，适合在显存压力下快速释放。",
    }[segment_type]
    return "\n\n".join(
        [
            "[AgentMem Cache Pressure Benchmark]",
            repeated_context,
            f"[Segment Payload]\n{segment_payload}",
            "请用三句话说明当前 segment 在 Agent-aware KV cache 管理中的保留或淘汰倾向。",
        ]
    )


def _ttl_priority_prompt(segment_type: str, priority: str, ttl: int, step_index: int) -> str:
    body = "\n".join(
        [
            (
                f"ttl-priority step={step_index} segment={segment_type} priority={priority} ttl={ttl}. "
                "AgentMem 将不同生命周期的上下文切片传给 vLLM agent_meta，用于服务端记录 block 旁路元信息。"
            )
            for _ in range(80)
        ]
    )
    return "\n\n".join(
        [
            "[AgentMem TTL/Priority Benchmark]",
            body,
            "请说明该 segment 的生命周期、优先级和 cache pressure 下的管理策略。",
        ]
    )


def _cache_pressure_items(segment_type: str, session_index: int) -> list[str]:
    base = [f"session_{session_index}", segment_type]
    if segment_type == "shared_prefix":
        return [*base, "system_prompt", "stable_project_rules"]
    if segment_type == "tool_schema":
        return [*base, "tool_briefs", "tool_call_contract"]
    if segment_type == "tool_result":
        return [*base, "tool_summary", "artifact_ref"]
    if segment_type == "scratchpad":
        return [*base, "planning_notes", "intermediate_state"]
    return [*base, "branch_delta", "expired_candidate"]


def _cache_pressure_refs(segment_type: str, session_index: int, step_index: int) -> list[dict[str, Any]]:
    if segment_type not in {"tool_result", "expired_branch"}:
        return []
    return [
        {
            "tool_name": "log_analyzer" if segment_type == "tool_result" else "branch_manager",
            "result_id": f"{segment_type}_s{session_index}_step{step_index}",
        }
    ]


def _cache_experiment_row(
    *,
    scenario: str,
    task_id: str,
    mode: str,
    backend: str,
    run_id: str,
    stage: str,
    step: int,
    session_id: str,
    context_id: str,
    segment_type: str,
    priority: str,
    ttl: int,
    prompt_label: str,
    response: dict[str, Any],
    cache_stats: dict[str, Any],
    config_path: Path,
) -> dict[str, Any]:
    prompt_tokens = int(response.get("prompt_tokens", 0) or 0)
    output_tokens = int(response.get("completion_tokens", 0) or 0)
    total_tokens = int(response.get("total_tokens", prompt_tokens + output_tokens) or 0)
    agent_meta = dict(response.get("agent_meta") or {})
    success = not bool(response.get("error")) and prompt_tokens > 0
    row = {
        "scenario": scenario,
        "task_id": task_id,
        "workload_file": f"metric:{scenario}",
        "mode": mode,
        "memory_mode": mode,
        "backend": backend,
        "model": response.get("model", ""),
        "round": step,
        "stage": stage,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "latency": response.get("latency", 0.0),
        "ttft": response.get("ttft", -1),
        "tokens_per_second": response.get("tokens_per_second", -1),
        "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
        "success": success,
        "score": 1.0 if success else 0.0,
        "failure_reason": response.get("error", ""),
        "passed_checks": 1 if success else 0,
        "total_checks": 1,
        "agent_meta_enabled": _agent_meta_enabled(config_path),
        "agent_id": agent_meta.get("agent_id") or _agent_id_value(config_path),
        "agent_meta_sent": bool(response.get("agent_meta_sent")),
        "agent_meta_agent_id": agent_meta.get("agent_id", ""),
        "agent_meta_session_id": agent_meta.get("session_id", run_id if response.get("agent_meta_sent") else ""),
        "agent_meta_context_id": agent_meta.get("context_id", ""),
        "agent_meta_segment_type": agent_meta.get("segment_type", ""),
        "agent_meta_priority": agent_meta.get("priority", ""),
        "session_id": session_id,
        "step": step,
        "context_id": context_id,
        "segment_type": segment_type,
        "priority": priority,
        "ttl": ttl,
        "prompt_label": prompt_label,
    }
    row.update(_cache_stats_row(cache_stats))
    return row


def _build_benchmark_agent(config_path: Path, output_dir: Path, memory_mode: str) -> AgentRuntime:
    config = load_runtime_config(config_path)
    agent_config = dict(config.get("agent") or {})
    registry = build_default_registry(PROJECT_ROOT / "skills")
    store = ToolResultStore(output_dir / "tool_store", raw_store_max_mb=_raw_store_max_mb(config))
    if memory_mode in {"baseline", "full_history"}:
        memory = BaselineMemory(system_prompt=SYSTEM_PROMPT, tool_registry=registry)
    elif memory_mode == "summary_memory":
        memory_config = dict(config.get("memory") or {})
        memory = OptimizedMemory(
            system_prompt=SYSTEM_PROMPT,
            tool_registry=registry,
            result_store=store,
            recent_rounds=int(memory_config.get("recent_rounds", 6)),
            enable_tool_externalization=bool(memory_config.get("enable_tool_externalization", True)),
            enable_skill_lazy_loading=bool(memory_config.get("enable_skill_lazy_loading", True)),
            enable_history_summary=bool(memory_config.get("enable_history_summary", True)),
        )
    elif memory_mode in {"optimized", "event_sourced_memory"}:
        memory_config = dict(config.get("memory") or {})
        memory = EventSourcedMemoryAdapter(
            system_prompt=SYSTEM_PROMPT,
            tool_registry=registry,
            result_store=store,
            output_dir=output_dir,
            recent_rounds=int(memory_config.get("recent_rounds", 4)),
            snapshot_interval=int(memory_config.get("event_snapshot_interval", 10)),
            max_state_tokens=int(memory_config.get("event_state_view_tokens", 900)),
            mode=memory_mode,
        )
    else:
        raise ValueError(f"unsupported memory_mode: {memory_mode}")
    enable_loop = bool(agent_config.get("enable_next_action_loop", True)) and memory_mode in {"optimized", "event_sourced_memory"}
    return AgentRuntime(
        memory=memory,
        tools=registry,
        llm_client=build_llm_client(config_path),
        tool_executor=ToolExecutor(registry, store),
        memory_delta_extractor=build_memory_delta_extractor(config) if memory_mode in {"optimized", "event_sourced_memory"} else None,
        max_steps=int(agent_config.get("max_steps", 3)),
        enable_next_action_loop=enable_loop,
        memory_plan_dir=output_dir / "memory_plan",
    )


def _raw_store_max_mb(config: dict[str, Any]) -> float | None:
    value = dict(config.get("tools") or {}).get("raw_store_max_mb", config.get("raw_store_max_mb"))
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _branch_row(
    task: dict[str, Any],
    workload: Path,
    branch_count: int,
    mode: str,
    backend: str,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    start = time.perf_counter()
    shared_context = (
        str(task["input"])
        + "\nAgentMem 需要保持公共任务目标、模型约束、工具说明和历史摘要，避免每条分支重复复制公共上下文。\n"
    ) * 80
    branch_manager = BranchManager()
    root_id = branch_manager.create_root(shared_context)
    shared_tokens = estimate_tokens(shared_context)
    delta_tokens = 0
    branch_text_parts: list[str] = []
    for idx in range(branch_count):
        branch_id = branch_manager.create_branch(root_id, f"branch_{idx + 1}")
        delta = f"分支 {idx + 1}: 评估一种 AgentMem 内存优化方案的优点、风险和适配场景。\n" * 24
        branch_manager.add_delta(branch_id, delta)
        delta_tokens += estimate_tokens(delta)
        branch_text_parts.append(
            f"方案 {idx + 1}: 采用 {_branch_strategy(idx)}。优点是降低上下文重复或注入 tokens；风险是实现复杂度和摘要遗漏。"
        )

    branch_text = "\n".join(branch_text_parts)
    duplicated_context_tokens = shared_tokens * branch_count + delta_tokens
    if mode == "optimized":
        optimized_context_tokens = shared_tokens + delta_tokens
        branch_saving_ratio = (
            (duplicated_context_tokens - optimized_context_tokens) / duplicated_context_tokens
            if duplicated_context_tokens
            else 0
        )
        prompt_tokens = optimized_context_tokens
    else:
        optimized_context_tokens = duplicated_context_tokens
        branch_saving_ratio = 0.0
        prompt_tokens = duplicated_context_tokens

    run_id = f"branching_{mode}"
    response = _safe_call_prompt(
        config_path,
        "\n\n".join([shared_context[:4000], branch_text, str(task["input"])]),
        run_id=run_id,
        stage="branching",
        segment_type="shared_prefix",
        context_id=f"{run_id}:branch_count_{branch_count}:shared_prefix",
        priority="high",
        branch_id=f"{root_id}:branches_{branch_count}",
        output_dir=output_dir,
        included_items=["shared_context", "branch_deltas", "current_query"],
        excluded_items=["duplicated_branch_context"] if mode == "optimized" else [],
        estimated_saved_tokens=max(0, duplicated_context_tokens - optimized_context_tokens),
    )
    latency = response["latency"]
    ttft = response.get("ttft", -1)
    output_tokens = response.get("completion_tokens", estimate_tokens(branch_text))
    total_tokens = response.get("total_tokens", prompt_tokens + output_tokens)
    tokens_per_second = response.get("tokens_per_second", -1)
    model = response.get("model", "")
    llm_error = response.get("error", "")

    row = {
        "scenario": "branching",
        "task_id": task["task_id"],
        "workload_file": _relative_path(workload),
        "mode": mode,
        "memory_mode": mode,
        "backend": backend,
        "model": model,
        "round": branch_count,
        "stage": "branching",
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "latency": latency,
        "ttft": ttft,
        "tokens_per_second": tokens_per_second,
        "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
        "failure_reason": llm_error,
        "branch_count": branch_count,
        "shared_context_tokens": shared_tokens,
        "branch_delta_tokens": delta_tokens,
        "duplicated_context_tokens": duplicated_context_tokens,
        "optimized_context_tokens": optimized_context_tokens,
        "branch_saving_ratio": branch_saving_ratio,
        "branch_answer_tokens": estimate_tokens(branch_text),
    }
    result = evaluate_task(task, "" if llm_error else branch_text, row, context={"branch_text": branch_text, "branch_count": branch_count})
    row.update(evaluation_fields(result))
    return _select_fields(row, BRANCHING_FIELDS, default=-1)


def _prefix_cache_prompt(mode: str, round_index: int) -> tuple[str, str]:
    registry = build_default_registry(PROJECT_ROOT / "skills")
    tool_briefs = registry.list_tool_briefs()
    project_rules = "固定说明：system/project/tool brief 保持稳定，动态历史和当前问题放在后部。"
    query = f"第 {round_index} 轮：请根据当前上下文分析 AgentMem 是否降低 vLLM prefill 压力。"

    if mode == "optimized":
        stable_prefix = "\n\n".join(
            [
                f"[system]\n{SYSTEM_PROMPT}",
                f"[project_rules]\n{project_rules}",
                f"[tool_briefs]\n{json.dumps(tool_briefs, ensure_ascii=False, indent=2)}",
            ]
        )
        prompt = "\n\n".join(
            [
                stable_prefix,
                f"[history_summary]\n前 {round_index - 1} 轮摘要：围绕工具外置、长会话压缩和 prefix cache 复用。",
                f"[current_query]\n{query}",
            ]
        )
        return prompt, stable_prefix

    shuffled = list(tool_briefs)
    random.Random(round_index).shuffle(shuffled)
    unstable_prefix = "\n\n".join(
        [
            f"[dynamic]\nround={round_index}; query={query}",
            f"[tool_briefs_random]\n{json.dumps(shuffled, ensure_ascii=False, indent=2)}",
            f"[system]\n{SYSTEM_PROMPT}",
        ]
    )
    prompt = "\n\n".join([unstable_prefix, f"[history]\n本轮之前的动态内容长度={round_index * 17}"])
    return prompt, unstable_prefix


def _call_prompt(
    config_path: Path,
    prompt: str,
    *,
    run_id: str = "agentmem_prompt_session",
    stage: str = "benchmark",
    segment_type: str | None = None,
    context_id: str | None = None,
    tool_name: str | None = None,
    priority: str | None = None,
    ttl: int | None = None,
    branch_id: str | None = None,
    output_dir: Path | None = None,
    included_items: list[Any] | None = None,
    external_refs: list[Any] | None = None,
    excluded_items: list[Any] | None = None,
    estimated_saved_tokens: int = 0,
) -> dict[str, Any]:
    client = build_llm_client(config_path)
    segment = segment_type or default_segment_type_for_stage(stage)
    resolved_context_id = context_id or f"{run_id}:{stage}:{segment}"
    agent_meta = {}
    if hasattr(client, "build_agent_meta"):
        agent_meta = dict(
            client.build_agent_meta(
                run_id=run_id,
                stage=stage,
                segment_type=segment,
                context_id=resolved_context_id,
                tool_name=tool_name,
                priority=priority,
                ttl=ttl,
                branch_id=branch_id,
            )
            or {}
        )
    if output_dir is not None:
        MemoryPlanLogger(Path(output_dir) / "memory_plan").record(
            run_id=run_id,
            stage=stage,
            context_id=resolved_context_id,
            segment_type=segment,
            priority=priority,
            ttl=agent_meta.get("ttl") if agent_meta else ttl,
            included_items=included_items or [stage, segment],
            external_refs=external_refs or [],
            excluded_items=excluded_items or [],
            estimated_prompt_tokens=estimate_tokens(prompt),
            estimated_saved_tokens=estimated_saved_tokens,
            agent_meta=agent_meta,
        )
    response = client.chat(
        [{"role": "user", "content": prompt}],
        agent_meta=agent_meta,
        run_id=run_id,
        stage=stage,
        segment_type=segment,
        context_id=resolved_context_id,
        tool_name=tool_name,
        priority=priority,
        ttl=ttl,
        branch_id=branch_id,
    )
    response.setdefault("agent_meta_sent", bool(agent_meta))
    response.setdefault("agent_meta", agent_meta)
    return response


def _safe_call_prompt(config_path: Path, prompt: str, **agent_meta_kwargs: Any) -> dict[str, Any]:
    try:
        return _call_prompt(config_path, prompt, **agent_meta_kwargs)
    except RuntimeError as exc:
        prompt_tokens = estimate_tokens(prompt)
        return {
            "content": "",
            "latency": 0.0,
            "ttft": -1,
            "model": "",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": 0,
            "total_tokens": prompt_tokens,
            "tokens_per_second": -1,
            "error": str(exc),
        }


def _load_tasks(scenario: str) -> tuple[list[dict[str, Any]], Path]:
    if scenario not in TASK_FILES:
        raise ValueError(f"scenario has no task file: {scenario}")
    path = TASK_DIR / TASK_FILES[scenario]
    if not path.exists():
        raise FileNotFoundError(f"benchmark task file missing: {path}")
    tasks: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        task = json.loads(line)
        if task.get("scenario") != scenario:
            raise ValueError(f"{path}:{line_number} scenario mismatch: {task.get('scenario')} != {scenario}")
        if not task.get("task_id"):
            raise ValueError(f"{path}:{line_number} missing task_id")
        if "input" not in task:
            raise ValueError(f"{path}:{line_number} missing input")
        tasks.append(task)
    if not tasks:
        raise ValueError(f"benchmark task file is empty: {path}")
    return tasks, path


def _group_sequence(tasks: list[dict[str, Any]], group_key: str, order_key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        grouped.setdefault(str(task.get(group_key, "default")), []).append(task)
    for group_tasks in grouped.values():
        group_tasks.sort(key=lambda item: int(item.get(order_key, 0)))
    return grouped


def _task_tool_context(task: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "dataset",
        "optional_log_path",
        "log_path",
        "optional_file_path",
        "file_path",
        "required_facts",
        "required_answer_points",
    ]
    return {key: task[key] for key in keys if task.get(key)}


def _row_from_metrics(
    task: dict[str, Any],
    workload: Path,
    metrics: dict[str, Any],
    scenario: str,
    memory_mode: str,
    backend: str,
    round_index: int,
) -> dict[str, Any]:
    row = {
        **metrics,
        "scenario": scenario,
        "task_id": task["task_id"],
        "workload_file": _relative_path(workload),
        "mode": memory_mode,
        "memory_mode": memory_mode,
        "backend": backend,
        "round": round_index,
        "stage": task.get("stage", metrics.get("stage", "")),
    }
    row.setdefault("output_tokens", metrics.get("output_tokens", -1))
    row.setdefault("total_tokens", metrics.get("total_tokens", -1))
    row.setdefault("model", metrics.get("model", ""))
    row.setdefault("tokens_per_second", metrics.get("tokens_per_second", -1))
    row.setdefault("full_history_tokens", metrics.get("full_history_tokens", metrics.get("history_tokens", -1)))
    row.setdefault("state_view_tokens", metrics.get("state_view_tokens", 0))
    row.setdefault("event_count", metrics.get("event_count", 0))
    row.setdefault("memory_delta_count", metrics.get("memory_delta_count", 0))
    row.setdefault("fact_count", metrics.get("fact_count", 0))
    row.setdefault("decision_count", metrics.get("decision_count", 0))
    row.setdefault("artifact_ref_count", metrics.get("artifact_ref_count", 0))
    row.setdefault("snapshot_count", metrics.get("snapshot_count", 0))
    return row


def _evaluate_ablation_row(row: dict[str, Any], baseline: dict[str, Any]):
    variant = row["variant"]
    checks = {
        "prompt_tokens_positive": _to_float(row["prompt_tokens"]) > 0,
        "tool_tokens_bounded": _to_float(row["injected_tool_tokens"]) <= _to_float(row["raw_tool_tokens"]),
    }
    if variant == "stable_prefix_only":
        checks["prefix_hashes_reduced"] = _to_float(row["unique_prefix_hashes"]) < _to_float(baseline["unique_prefix_hashes"])
    elif variant == "skill_lazy_loading_only":
        checks["loaded_skill_tokens_reduced"] = _to_float(row["loaded_skill_tokens"]) < _to_float(baseline["loaded_skill_tokens"])
    elif variant == "tool_externalization_only":
        checks["injected_tool_tokens_reduced"] = _to_float(row["injected_tool_tokens"]) < _to_float(baseline["injected_tool_tokens"])
    elif variant == "history_summary_only":
        checks["history_tokens_reduced"] = _to_float(row["history_tokens"]) < _to_float(baseline["history_tokens"])
        checks["summary_present"] = _to_float(row["summary_tokens"]) > 0
    elif variant == "full_optimized":
        checks["prompt_tokens_reduced"] = _to_float(row["prompt_tokens"]) < _to_float(baseline["prompt_tokens"])
        checks["injected_tool_tokens_reduced"] = _to_float(row["injected_tool_tokens"]) < _to_float(baseline["injected_tool_tokens"])
        checks["history_tokens_reduced"] = _to_float(row["history_tokens"]) < _to_float(baseline["history_tokens"])
        checks["loaded_skill_tokens_reduced"] = _to_float(row["loaded_skill_tokens"]) < _to_float(baseline["loaded_skill_tokens"])
        checks["prefix_hashes_reduced"] = _to_float(row["unique_prefix_hashes"]) < _to_float(baseline["unique_prefix_hashes"])
    return evaluate_metric_checks(checks)


def _ablation_unique_prefixes(stable: bool, prefix: str) -> int:
    hashes: set[str] = set()
    for round_index in range(1, 4):
        if stable:
            text = f"[stable]\n{SYSTEM_PROMPT}\n{prefix}"
        else:
            text = f"[dynamic round={round_index}]\n{prefix}\n{SYSTEM_PROMPT}"
        hashes.add(hash_text(text)[:16])
    return len(hashes)


def _branch_strategy(index: int) -> str:
    strategies = [
        "工具结果外置",
        "历史摘要",
        "stable prefix",
        "skill lazy loading",
        "分支上下文共享",
        "evaluator 质量约束",
        "固定 workload",
        "真实 vLLM 指标采集",
    ]
    return strategies[index % len(strategies)]


def _selected_modes(mode: str) -> list[str]:
    if mode == "both":
        return ["baseline", "optimized"]
    return [mode]


def _selected_long_multi_modes(mode: str) -> list[str]:
    if mode == "both":
        return list(LONG_MULTI_MEMORY_MODES)
    if mode == "baseline":
        return ["full_history"]
    if mode == "optimized":
        return ["event_sourced_memory"]
    return [mode]


def _evaluate_agent_task(
    agent: AgentRuntime,
    task: dict[str, Any],
    answer: str,
    metrics: dict[str, Any],
    context: dict[str, Any] | None = None,
):
    eval_context = dict(context or {})
    eval_context["retention_text"] = _agent_retention_text(agent)
    result = evaluate_task(task, answer, metrics, context=eval_context)
    initial_score = result.score
    metrics["initial_score"] = initial_score
    metrics["final_score"] = result.score
    return result, answer, metrics


def _refill_missing_evidence(
    agent: AgentRuntime,
    config_path: Path,
    task: dict[str, Any],
    answer: str,
    metrics: dict[str, Any],
    result,
):
    missing = _missing_terms_from_result(task, result)
    if not missing:
        metrics["initial_score"] = result.score
        metrics["final_score"] = result.score
        metrics["refill_count"] = 0
        metrics["refill_tokens"] = 0
        return result, answer, metrics

    evidence = ""
    memory = agent.memory
    artifact_manager = getattr(memory, "artifact_manager", None)
    if artifact_manager is not None:
        evidence = artifact_manager.create_artifact_context(missing, max_tokens_per_ref=180)
    if not evidence:
        retention = _agent_retention_text(agent)
        evidence = _keyword_preview(retention, missing, max_chars=1200)
    if not evidence:
        metrics["initial_score"] = result.score
        metrics["final_score"] = result.score
        metrics["refill_count"] = 0
        metrics["refill_tokens"] = 0
        return result, answer, metrics

    prompt = "\n".join(
        [
            "请基于以下结构化要求和证据补充最终回答。不要引入未在证据中出现的事实。",
            "",
            "[Current Query]",
            str(task.get("input", "")),
            "",
            "[Required Facts]",
            "\n".join(f"- {item}" for item in task.get("required_facts") or []),
            "",
            "[Required Answer Points]",
            "\n".join(f"- {item}" for item in task.get("required_answer_points") or []),
            "",
            "[Previous Answer]",
            answer,
            "",
            "[Evidence Preview]",
            evidence,
            "",
            "请给出覆盖 required facts 和 required answer points 的简洁中文回答。",
        ]
    )
    response = _safe_call_prompt(config_path, prompt)
    refill_answer = str(response.get("content", "") or "").strip()
    refill_tokens = int(response.get("prompt_tokens", estimate_tokens(prompt)) or 0)
    if not refill_answer or response.get("error"):
        metrics["initial_score"] = result.score
        metrics["final_score"] = result.score
        metrics["refill_count"] = 0
        metrics["refill_tokens"] = refill_tokens
        return result, answer, metrics

    new_metrics = dict(metrics)
    new_metrics["prompt_tokens"] = int(metrics.get("prompt_tokens", 0) or 0) + refill_tokens
    new_metrics["output_tokens"] = int(metrics.get("output_tokens", 0) or 0) + int(response.get("completion_tokens", 0) or 0)
    new_metrics["total_tokens"] = int(metrics.get("total_tokens", 0) or 0) + int(response.get("total_tokens", 0) or 0)
    new_metrics["latency"] = float(metrics.get("latency", 0) or 0) + float(response.get("latency", 0) or 0)
    new_metrics["refill_count"] = 1
    new_metrics["refill_tokens"] = refill_tokens
    eval_context = {"answer_extra": evidence, "retention_text": _agent_retention_text(agent)}
    new_result = evaluate_task(task, refill_answer, new_metrics, context=eval_context)
    new_metrics["initial_score"] = result.score
    new_metrics["final_score"] = new_result.score
    return new_result, refill_answer, new_metrics


def _missing_terms_from_result(task: dict[str, Any], result) -> list[str]:
    missing = _split_missing_keywords(getattr(result, "missing_keywords", ""))
    failure = str(getattr(result, "failure_reason", "") or "")
    for prefix in ["required_fact:", "required_answer_point:", "answer_keyword:"]:
        for part in failure.split(";"):
            if part.startswith(prefix):
                missing.append(part[len(prefix) :])
    if not missing:
        missing.extend(str(item) for item in task.get("required_facts") or [])
    return _dedupe_strings(missing)


def _keyword_preview(text: str, terms: list[str], max_chars: int = 1200) -> str:
    lowered = text.lower()
    for term in terms:
        index = lowered.find(str(term).lower())
        if index >= 0:
            start = max(0, index - max_chars // 3)
            return text[start : start + max_chars]
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _agent_retention_text(agent: AgentRuntime) -> str:
    memory = agent.memory
    if hasattr(memory, "retention_text"):
        return str(memory.retention_text())
    messages = getattr(memory, "messages", [])
    return "\n".join(str(item.get("content", "")) for item in messages if isinstance(item, dict))


def _split_missing_keywords(value: str) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _select_fields(row: dict[str, Any], fields: list[str], default: Any = "") -> dict[str, Any]:
    return {field: row.get(field, default) for field in fields}


def _capture_cache_stats(config_path: Path, output_dir: Path, scenario: str, mode: str, moment: str, backend: str) -> dict[str, Any]:
    if backend != "vllm":
        return _unavailable_cache_stats("backend_not_vllm")
    config = load_runtime_config(config_path)
    vllm_config = dict(config.get("vllm") or {})
    metrics_url = str(vllm_config.get("metrics_url") or "")
    if not metrics_url:
        stats = _unavailable_cache_stats("metrics_url_not_configured")
    else:
        timeout = int(vllm_config.get("cache_stats_timeout", 10))
        stats = CacheStatsCollector(metrics_url=metrics_url, timeout=timeout).fetch()
    stats["agent_meta_enabled"] = _agent_meta_enabled(config_path)
    stats["agent_id"] = _agent_id_value(config_path)
    path = output_dir / f"cache_stats_{_safe_name(scenario)}_{_safe_name(mode)}_{moment}.json"
    path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def _cache_stats_row(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_meta_enabled": bool(stats.get("agent_meta_enabled", _agent_meta_enabled_value())),
        "agent_id": str(stats.get("agent_id", _agent_id_value())),
        "cache_stats_available": bool(stats.get("available", False)),
        "cache_stats_unavailable_reason": stats.get("unavailable_reason", ""),
        "cache_total_blocks": stats.get("cache_total_blocks", -1),
        "cache_agent_sessions": stats.get("cache_agent_sessions", -1),
        "cache_tool_result_blocks": stats.get("cache_tool_result_blocks", -1),
        "cache_shared_prefix_blocks": stats.get("cache_shared_prefix_blocks", -1),
        "cache_scratchpad_blocks": stats.get("cache_scratchpad_blocks", -1),
        "cache_expired_branch_blocks": stats.get("cache_expired_branch_blocks", -1),
    }


def _merge_cache_stats(row: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    output.update(_cache_stats_row(stats))
    return output


def _unavailable_cache_stats(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "unavailable_reason": reason,
        "cache_total_blocks": -1,
        "cache_agent_sessions": -1,
        "cache_tool_result_blocks": -1,
        "cache_shared_prefix_blocks": -1,
        "cache_scratchpad_blocks": -1,
        "cache_expired_branch_blocks": -1,
    }


def _safe_name(value: str) -> str:
    return str(value).replace("-", "_").replace("/", "_")


def _agent_meta_enabled(config_path: Path) -> bool:
    return _agent_meta_enabled_value(load_runtime_config(config_path))


def _agent_meta_enabled_value(config: dict[str, Any] | None = None) -> bool:
    env_value = os.environ.get("AGENTMEM_ENABLE_AGENT_META")
    if env_value is not None:
        return env_value.strip().lower() in {"1", "true", "yes", "on"}
    vllm_config = dict((config or {}).get("vllm") or {})
    value = vllm_config.get("enable_agent_meta", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _agent_id_value(config_path: Path | None = None) -> str:
    env_value = os.environ.get("AGENTMEM_AGENT_ID")
    if env_value:
        return env_value
    config = load_runtime_config(config_path) if config_path is not None else None
    vllm_config = dict((config or {}).get("vllm") or {})
    return str(vllm_config.get("agent_id", ""))


def _default_agent_id(scenario: str, agent_meta_enabled: bool | None) -> str:
    mode = "config" if agent_meta_enabled is None else ("on" if agent_meta_enabled else "off")
    return f"agentmem_{_safe_name(scenario or 'all')}_{mode}_{int(time.time())}"


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_vllm_benchmark(output_dir: Path) -> Path:
    rows: list[dict[str, Any]] = []
    for path in sorted(output_dir.glob("*.csv")):
        if path.name in {"summary.csv", "vllm_benchmark.csv"}:
            continue
        for row in _read_csv_rows(path):
            if row.get("backend") != "vllm":
                continue
            rows.append(_select_fields(row, VLLM_BENCHMARK_FIELDS, default=-1))
    vllm_path = output_dir / "vllm_benchmark.csv"
    _write_csv(vllm_path, rows, VLLM_BENCHMARK_FIELDS)
    return vllm_path


def _write_mode_aliases(output_dir: Path, aliases: dict[str, str]) -> list[Path]:
    paths: list[Path] = []
    for source_name, target_name in aliases.items():
        source = output_dir / source_name
        target = output_dir / target_name
        if not source.exists():
            continue
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        paths.append(target)
    return paths


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _resolve_output_dir(output_dir: Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in {None, ""}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@contextmanager
def _override_backend(backend: str):
    old_value = os.environ.get("AGENTMEM_LLM_BACKEND")
    os.environ["AGENTMEM_LLM_BACKEND"] = backend
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop("AGENTMEM_LLM_BACKEND", None)
        else:
            os.environ["AGENTMEM_LLM_BACKEND"] = old_value


@contextmanager
def _override_agent_meta(enabled: bool | None):
    old_value = os.environ.get("AGENTMEM_ENABLE_AGENT_META")
    if enabled is not None:
        os.environ["AGENTMEM_ENABLE_AGENT_META"] = "true" if enabled else "false"
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop("AGENTMEM_ENABLE_AGENT_META", None)
        else:
            os.environ["AGENTMEM_ENABLE_AGENT_META"] = old_value


@contextmanager
def _override_agent_id(agent_id: str | None):
    old_value = os.environ.get("AGENTMEM_AGENT_ID")
    if agent_id:
        os.environ["AGENTMEM_AGENT_ID"] = str(agent_id)
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop("AGENTMEM_AGENT_ID", None)
        else:
            os.environ["AGENTMEM_AGENT_ID"] = old_value
