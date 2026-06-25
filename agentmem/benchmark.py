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


SCENARIOS = {"tool-heavy", "long-session", "multi-stage", "branching", "prefix-cache", "ablation", "all"}
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
    "round",
    "stage",
    "prompt_tokens",
    "output_tokens",
    "total_tokens",
    "latency",
    "ttft",
    "peak_gpu_memory_mb",
    "success",
    "score",
    "failure_reason",
    "passed_checks",
    "total_checks",
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
]


@dataclass(frozen=True)
class BenchmarkOptions:
    scenario: str = "all"
    mode: str = "both"
    backend: str = "mock"
    repeat: int = 1
    output_dir: Path = PROJECT_ROOT / "results"
    config_path: Path = PROJECT_ROOT / "configs" / "config.yaml"


def run_benchmark(options: BenchmarkOptions) -> dict[str, Any]:
    if options.scenario not in SCENARIOS:
        raise ValueError(f"unsupported scenario: {options.scenario}")
    if options.mode not in MODES:
        raise ValueError(f"unsupported mode: {options.mode}")

    output_dir = _resolve_output_dir(options.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    repeat = max(1, int(options.repeat))
    backend = options.backend.replace("-", "_")

    paths: list[Path] = []
    scenarios = ["tool-heavy", "long-session", "multi-stage", "branching", "prefix-cache", "ablation"]
    if options.scenario != "all":
        scenarios = [options.scenario]

    with _override_backend(backend):
        for scenario in scenarios:
            if scenario == "tool-heavy":
                paths.extend(_run_tool_heavy(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "long-session":
                paths.extend(_run_long_session(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "multi-stage":
                paths.extend(_run_multi_stage(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "branching":
                paths.extend(_run_branching(output_dir, backend, options.mode, repeat))
            elif scenario == "prefix-cache":
                paths.extend(_run_prefix_cache(options.config_path, output_dir, backend, options.mode, repeat))
            elif scenario == "ablation":
                paths.append(_run_ablation(options.config_path, output_dir, backend))

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
        rows = []
        for repeat_index in range(repeat):
            for task_index, task in enumerate(tasks, start=1):
                agent = _build_benchmark_agent(config_path, output_dir, memory_mode)
                answer, metrics = agent.run(str(task["input"]), stage=str(task.get("stage", "tool_calling")))
                result = evaluate_task(task, answer, metrics)
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
                rows.append(_select_fields(row, TOOL_HEAVY_FIELDS, default=-1))
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
        rows: list[dict[str, Any]] = []
        for _ in range(repeat):
            for session_id, session_tasks in sessions.items():
                agent = _build_benchmark_agent(config_path, output_dir, memory_mode)
                for turn_index, task in enumerate(session_tasks, start=1):
                    answer, metrics = agent.run(str(task["input"]), stage=str(task.get("stage", "planning")))
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
                    rows.append(_select_fields(row, LONG_SESSION_FIELDS, default=-1))
        path = output_dir / f"long_session_{memory_mode}.csv"
        _write_csv(path, rows, LONG_SESSION_FIELDS)
        paths.append(path)
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
        rows: list[dict[str, Any]] = []
        for _ in range(repeat):
            for session_id, session_tasks in sessions.items():
                agent = _build_benchmark_agent(config_path, output_dir, memory_mode)
                completed_stages: list[str] = []
                for step_index, task in enumerate(session_tasks, start=1):
                    stage = str(task.get("stage", "planning"))
                    answer, metrics = agent.run(str(task["input"]), stage=stage)
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
                    rows.append(_select_fields(row, MULTI_STAGE_FIELDS, default=-1))
        path = output_dir / f"multi_stage_{memory_mode}.csv"
        _write_csv(path, rows, MULTI_STAGE_FIELDS)
        paths.append(path)
    return paths


def _run_branching(output_dir: Path, backend: str, mode: str, repeat: int) -> list[Path]:
    tasks, workload = _load_tasks("branching")
    paths: list[Path] = []
    combined_rows: list[dict[str, Any]] = []

    for memory_mode in _selected_modes(mode):
        rows: list[dict[str, Any]] = []
        for _ in range(repeat):
            for task in tasks:
                for branch_count in task.get("branch_counts") or [2, 4, 8]:
                    rows.append(_branch_row(task, workload, int(branch_count), memory_mode, backend))
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
    all_rows: list[dict[str, Any]] = []

    for memory_mode in _selected_modes(mode):
        rows = []
        total_rounds = repeat * 6
        for round_index in range(1, total_rounds + 1):
            prompt, stable_prefix = _prefix_cache_prompt(memory_mode, round_index)
            if backend == "mock":
                prompt_tokens = estimate_tokens(prompt)
                output_tokens = 0
                total_tokens = prompt_tokens
                latency = _simulated_latency(prompt_tokens, memory_mode)
                ttft = latency * 0.45
                vllm_metrics = dict(DEFAULT_VLLM_METRICS)
            else:
                response = _call_prompt(config_path, prompt)
                prompt_tokens = response["prompt_tokens"]
                output_tokens = response.get("completion_tokens", 0)
                total_tokens = response.get("total_tokens", prompt_tokens + output_tokens)
                latency = response["latency"]
                ttft = response.get("ttft", -1)
                vllm_metrics = fetch_vllm_metrics(metrics_url) if backend == "vllm" else dict(DEFAULT_VLLM_METRICS)

            row = {
                "scenario": "prefix-cache",
                "task_id": f"prefix_cache_round_{round_index:02d}",
                "workload_file": "metric:prefix-cache",
                "mode": memory_mode,
                "backend": backend,
                "round": round_index,
                "stage": "prefix_cache",
                "stable_prefix_hash": hash_text(stable_prefix)[:16],
                "stable_prefix_tokens": estimate_tokens(stable_prefix),
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "latency": latency,
                "ttft": ttft,
                "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
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
                            "prompt_tokens_positive": _to_float(row["prompt_tokens"]) > 0,
                            "stable_prefix_hash_present": bool(row["stable_prefix_hash"]),
                            "expected_prefix_pattern": unique_hashes == 1 if memory_mode == "optimized" else unique_hashes > 1,
                        }
                    )
                )
            )
        path = output_dir / f"prefix_cache_{memory_mode}.csv"
        rows = [_select_fields(row, PREFIX_CACHE_FIELDS, default=-1) for row in rows]
        _write_csv(path, rows, PREFIX_CACHE_FIELDS)
        paths.append(path)
        all_rows.extend(rows)

    if backend == "vllm":
        vllm_path = output_dir / "vllm_benchmark.csv"
        _write_csv(vllm_path, all_rows, PREFIX_CACHE_FIELDS)
        paths.append(vllm_path)
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
    for item in variants:
        prompt = "\n\n".join(item["parts"])
        prompt_tokens = estimate_tokens(prompt)
        if backend == "mock":
            latency = _simulated_latency(prompt_tokens, "optimized" if item["variant"] == "full_optimized" else "baseline")
            ttft = latency * 0.45
            output_tokens = 0
            total_tokens = prompt_tokens
        else:
            response = _call_prompt(config_path, prompt)
            latency = response["latency"]
            ttft = response.get("ttft", -1)
            output_tokens = response.get("completion_tokens", 0)
            total_tokens = response.get("total_tokens", prompt_tokens + output_tokens)
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
        }
        rows.append(row)

    baseline = next(row for row in rows if row["variant"] == "baseline")
    for row in rows:
        row.update(evaluation_fields(_evaluate_ablation_row(row, baseline)))

    path = output_dir / "ablation.csv"
    _write_csv(path, [_select_fields(row, ABLATION_FIELDS, default=-1) for row in rows], ABLATION_FIELDS)
    return path


def _build_benchmark_agent(config_path: Path, output_dir: Path, memory_mode: str) -> AgentRuntime:
    config = load_runtime_config(config_path)
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
    return AgentRuntime(
        memory=memory,
        tools=registry,
        llm_client=build_llm_client(config_path),
        tool_executor=ToolExecutor(registry, store),
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


def _branch_row(task: dict[str, Any], workload: Path, branch_count: int, mode: str, backend: str) -> dict[str, Any]:
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

    row = {
        "scenario": "branching",
        "task_id": task["task_id"],
        "workload_file": _relative_path(workload),
        "mode": mode,
        "backend": backend,
        "round": branch_count,
        "stage": "branching",
        "prompt_tokens": prompt_tokens,
        "output_tokens": estimate_tokens(branch_text),
        "total_tokens": prompt_tokens + estimate_tokens(branch_text),
        "latency": time.perf_counter() - start,
        "ttft": 0.0,
        "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
        "branch_count": branch_count,
        "shared_context_tokens": shared_tokens,
        "branch_delta_tokens": delta_tokens,
        "duplicated_context_tokens": duplicated_context_tokens,
        "optimized_context_tokens": optimized_context_tokens,
        "branch_saving_ratio": branch_saving_ratio,
        "branch_answer_tokens": estimate_tokens(branch_text),
    }
    result = evaluate_task(task, branch_text, row, context={"branch_text": branch_text, "branch_count": branch_count})
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


def _call_prompt(config_path: Path, prompt: str) -> dict[str, Any]:
    client = build_llm_client(config_path)
    return client.chat([{"role": "user", "content": prompt}])


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


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _simulated_latency(prompt_tokens: int, mode: str) -> float:
    multiplier = 0.000012 if mode == "optimized" else 0.000018
    return round(0.01 + prompt_tokens * multiplier, 6)


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
