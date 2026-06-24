from __future__ import annotations

from pathlib import Path
from typing import Any

from agentmem.memory.baseline_memory import BaselineMemory
from agentmem.memory.optimized_memory import OptimizedMemory
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
    results_root = _resolve_results_dir(root, config, results_dir)

    registry = build_default_registry(root / "skills")
    store = ToolResultStore(results_root / "tool_store")
    mode = memory_mode.lower()
    if mode == "baseline":
        memory = BaselineMemory(system_prompt=SYSTEM_PROMPT, tool_registry=registry)
    elif mode == "optimized":
        memory_config = dict(config.get("memory") or {})
        memory = OptimizedMemory(
            system_prompt=SYSTEM_PROMPT,
            tool_registry=registry,
            result_store=store,
            recent_rounds=int(memory_config.get("recent_rounds", 3)),
            enable_tool_externalization=bool(memory_config.get("enable_tool_externalization", True)),
            enable_skill_lazy_loading=bool(memory_config.get("enable_skill_lazy_loading", True)),
            enable_history_summary=bool(memory_config.get("enable_history_summary", True)),
        )
    else:
        raise ValueError(f"unsupported memory_mode: {memory_mode}")

    return AgentRuntime(
        memory=memory,
        tools=registry,
        llm_client=build_llm_client(config_file),
        tool_executor=ToolExecutor(registry, store),
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
