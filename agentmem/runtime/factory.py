from __future__ import annotations

from pathlib import Path
from typing import Any

from agentmem.event_memory.integration import EventSourcedMemoryAdapter
from agentmem.event_memory.extractor import build_memory_delta_extractor
from agentmem.memory.baseline_memory import BaselineMemory
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.runtime.agent import AgentRuntime
from agentmem.runtime.llm_factory import build_llm_client, load_runtime_config
from agentmem.tools.executor import ToolExecutor
from agentmem.tools.tool_registry import build_default_registry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_PROMPT = (
    "你是 AgentMem Runtime，用中文给出简洁可靠的回答。"
    "当工具返回大结果时，只引用 result_id 和摘要，不把原文重复写入回答。"
)


def build_agent(
    *,
    project_root: str | Path | None = None,
    config_path: str | Path | None = None,
    results_dir: str | Path | None = None,
    memory_mode: str = "optimized",
) -> AgentRuntime:
    """Build the core AgentMem runtime for CLI, tests and benchmarks."""
    root = Path(project_root) if project_root else PROJECT_ROOT
    config_file = Path(config_path) if config_path else root / "configs" / "config.yaml"
    config = load_runtime_config(config_file)
    agent_config = dict(config.get("agent") or {})
    results_root = _resolve_results_dir(root, config, results_dir)

    registry = build_default_registry(root / "skills")
    store = ToolResultStore(results_root / "tool_store", raw_store_max_mb=_raw_store_max_mb(config))
    mode = memory_mode.lower()
    if mode == "baseline":
        memory = BaselineMemory(system_prompt=SYSTEM_PROMPT, tool_registry=registry)
    elif mode == "optimized":
        memory_config = dict(config.get("memory") or {})
        memory = EventSourcedMemoryAdapter(
            system_prompt=SYSTEM_PROMPT,
            tool_registry=registry,
            result_store=store,
            output_dir=results_root,
            recent_rounds=int(memory_config.get("recent_rounds", 4)),
            snapshot_interval=int(memory_config.get("event_snapshot_interval", 10)),
            max_state_tokens=int(memory_config.get("event_state_view_tokens", 900)),
            mode="optimized",
        )
    else:
        raise ValueError(f"unsupported memory_mode: {memory_mode}")

    enable_loop = bool(agent_config.get("enable_next_action_loop", True)) and mode == "optimized"
    return AgentRuntime(
        memory=memory,
        tools=registry,
        llm_client=build_llm_client(config_file),
        tool_executor=ToolExecutor(registry, store),
        memory_delta_extractor=build_memory_delta_extractor(config) if mode == "optimized" else None,
        max_steps=int(agent_config.get("max_steps", 3)),
        enable_next_action_loop=enable_loop,
    )


def _resolve_results_dir(root: Path, config: dict[str, Any], results_dir: str | Path | None) -> Path:
    if results_dir is not None:
        path = Path(results_dir)
    else:
        benchmark_config = dict(config.get("benchmark") or {})
        path = Path(str(benchmark_config.get("output_dir", benchmark_config.get("results_dir", "results"))))
    if not path.is_absolute():
        path = root / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _raw_store_max_mb(config: dict[str, Any]) -> float | None:
    value = dict(config.get("tools") or {}).get("raw_store_max_mb", config.get("raw_store_max_mb"))
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
