from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmem.memory.branch_manager import BranchManager
from agentmem.memory.memory_object import estimate_tokens


def main() -> None:
    results_dir = ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    output = results_dir / "branch_benchmark.csv"
    rows = []
    shared = "\n".join(
        f"共享上下文 {idx}: system prompt、项目约束、工具 brief、历史摘要和任务目标。"
        for idx in range(300)
    )

    for count in [2, 4, 8]:
        manager = BranchManager()
        root_id = manager.create_root(shared)
        baseline_tokens = 0
        for idx in range(count):
            branch_id = manager.create_branch(root_id, f"branch_{idx}")
            delta = f"分支 {idx}: 只保存当前方案的推理差异和局部工具摘要。"
            manager.add_delta(branch_id, delta)
            baseline_tokens += estimate_tokens(shared + "\n" + delta)

        optimized_tokens = estimate_tokens(shared) + sum(
            estimate_tokens(delta)
            for node in manager.branches.values()
            for delta in node.deltas
        )
        rows.append(
            {
                "branch_count": count,
                "baseline_tokens": baseline_tokens,
                "optimized_tokens": optimized_tokens,
                "sharing_ratio": manager.calculate_sharing_ratio(),
                "token_reduction_ratio": (baseline_tokens - optimized_tokens) / baseline_tokens,
            }
        )

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"branch benchmark written to {output}")


if __name__ == "__main__":
    main()
