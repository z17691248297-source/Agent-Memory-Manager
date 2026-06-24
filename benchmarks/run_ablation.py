from __future__ import annotations

import csv
from pathlib import Path

from common import RESULTS_DIR, SYSTEM_PROMPT, run_agent_benchmark
from agentmem.memory.baseline_memory import BaselineMemory
from agentmem.memory.optimized_memory import OptimizedMemory
from agentmem.metrics.collector import FIELDS


def main() -> None:
    rows: list[dict] = []
    experiments = {
        "baseline_full_tool_prompt": lambda registry, store: BaselineMemory(SYSTEM_PROMPT, registry),
        "tool_brief_only": lambda registry, store: OptimizedMemory(
            SYSTEM_PROMPT,
            registry,
            store,
            enable_tool_externalization=False,
            enable_skill_lazy_loading=False,
        ),
        "skill_lazy_loading": lambda registry, store: OptimizedMemory(
            SYSTEM_PROMPT,
            registry,
            store,
            enable_tool_externalization=False,
            enable_skill_lazy_loading=True,
        ),
        "tool_externalization": lambda registry, store: OptimizedMemory(
            SYSTEM_PROMPT,
            registry,
            store,
            enable_tool_externalization=True,
            enable_skill_lazy_loading=False,
        ),
        "tool_externalization_plus_chunk_search": lambda registry, store: OptimizedMemory(
            SYSTEM_PROMPT,
            registry,
            store,
            enable_tool_externalization=True,
            enable_skill_lazy_loading=True,
        ),
        "full_agentmem_tool_system": lambda registry, store: OptimizedMemory(
            SYSTEM_PROMPT,
            registry,
            store,
            enable_tool_externalization=True,
            enable_skill_lazy_loading=True,
        ),
    }

    for name, factory in experiments.items():
        temp_path = RESULTS_DIR / f"ablation_{name}.csv"
        run_agent_benchmark(
            memory_factory=factory,
            output_csv=temp_path,
            workload_files=("tool_call.jsonl",),
            experiment=name,
        )
        with temp_path.open("r", encoding="utf-8", newline="") as file:
            rows.extend(csv.DictReader(file))
        temp_path.unlink(missing_ok=True)

    output = RESULTS_DIR / "ablation.csv"
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"ablation metrics written to {Path(output)}")


if __name__ == "__main__":
    main()
