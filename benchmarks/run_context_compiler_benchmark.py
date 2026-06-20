from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.context_compiler import ContextCompiler
from agent.policies import POLICIES
from benchmarks.scenarios import build_all_scenarios


RESULTS_DIR = Path("benchmarks/results")


def main() -> None:
    # 每次运行都会重新生成 prompt、trace 和 artifact。
    # 这些文件用于本地分析，不作为源码提交。
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_store = ArtifactStore(RESULTS_DIR / "artifacts")
    compiler = ContextCompiler(artifact_store)
    scenarios = build_all_scenarios()

    rows: list[dict] = []
    for scenario in scenarios:
        for policy in POLICIES.values():
            # 同一个场景用多种策略分别编译，形成 baseline / optimized 对照。
            compiled = compiler.compile(
                scenario.memory_objects,
                policy,
                active_branch_id=scenario.active_branch_id,
            )
            row = {
                "scenario_id": scenario.scenario_id,
                "description": scenario.description,
                **asdict(compiled.trace),
            }
            rows.append(row)

            # prompt 文件用于人工查看“最终喂给模型的上下文”。
            # trace 文件用于查看每个 MemoryObject 的去向和 token 变化。
            prompt_path = RESULTS_DIR / f"{scenario.scenario_id}.{policy.name}.prompt.txt"
            trace_path = RESULTS_DIR / f"{scenario.scenario_id}.{policy.name}.trace.json"
            prompt_path.write_text(compiled.prompt, encoding="utf-8")
            trace_path.write_text(
                json.dumps(row, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    summary_path = RESULTS_DIR / "context_compiler_summary.json"
    summary_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print_table(rows)
    print(f"\nsummary: {summary_path}")


def print_table(rows: list[dict]) -> None:
    headers = [
        "scenario",
        "policy",
        "tokens",
        "stable",
        "dynamic",
        "artifact_refs",
        "saved",
        "dropped",
        "artifacts",
    ]
    print(" | ".join(headers))
    print(" | ".join("---" for _ in headers))
    for row in rows:
        values = [
            row["scenario_id"],
            row["policy_name"],
            str(row["total_input_tokens"]),
            str(row["stable_prefix_tokens"]),
            str(row["dynamic_context_tokens"]),
            str(row["artifact_ref_tokens"]),
            str(row["artifact_saved_tokens"]),
            str(row["dropped_tokens"]),
            str(row["artifact_count"]),
        ]
        print(" | ".join(values))


if __name__ == "__main__":
    main()
