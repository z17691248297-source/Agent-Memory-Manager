from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmem.memory.baseline_memory import BaselineMemory
from agentmem.memory.optimized_memory import OptimizedMemory
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.metrics.collector import MetricsCollector
from agentmem.runtime.agent import AgentRuntime
from agentmem.runtime.factory import SYSTEM_PROMPT
from agentmem.runtime.llm_factory import build_llm_client
from agentmem.tools.executor import ToolExecutor
from agentmem.tools.tool_registry import build_default_registry


RESULTS_DIR = ROOT / "results"
WORKLOAD_DIR = ROOT / "benchmarks" / "workloads"


def load_workload(file_name: str) -> list[dict]:
    path = WORKLOAD_DIR / file_name
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_workloads(file_names: Iterable[str]) -> list[dict]:
    rows: list[dict] = []
    for file_name in file_names:
        rows.extend(load_workload(file_name))
    return rows


def run_agent_benchmark(
    memory_factory: Callable,
    output_csv: str | Path,
    workload_files: Iterable[str] = ("multi_turn.jsonl", "tool_call.jsonl"),
    experiment: str = "",
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    registry = build_default_registry(ROOT / "skills")
    store = ToolResultStore(RESULTS_DIR / "tool_store")
    memory = memory_factory(registry, store)
    executor = ToolExecutor(registry, store)
    agent = AgentRuntime(memory=memory, tools=registry, llm_client=build_llm_client(ROOT / "configs" / "config.yaml"), tool_executor=executor)
    collector = MetricsCollector(output_csv)

    for item in load_workloads(workload_files):
        _, metrics = agent.run(item["input"], stage=item.get("stage", "planning"))
        metrics["experiment"] = experiment
        collector.record(metrics)
    return collector.write_csv()


def baseline_memory_factory(registry, store) -> BaselineMemory:
    return BaselineMemory(system_prompt=SYSTEM_PROMPT, tool_registry=registry)


def optimized_memory_factory(registry, store) -> OptimizedMemory:
    return OptimizedMemory(
        system_prompt=SYSTEM_PROMPT,
        tool_registry=registry,
        result_store=store,
        recent_rounds=3,
    )
