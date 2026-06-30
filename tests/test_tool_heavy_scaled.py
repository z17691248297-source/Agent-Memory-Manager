from __future__ import annotations

import json

from agentmem.benchmark import PROJECT_ROOT
from agentmem.cli import main
from agentmem.memory.memory_object import estimate_tokens


def test_tool_heavy_scaled_dataset_contains_required_facts() -> None:
    task_path = PROJECT_ROOT / "benchmarks" / "tasks" / "tool_heavy.jsonl"
    dataset_path = PROJECT_ROOT / "benchmarks" / "fixtures" / "tool_heavy_scaled.log"
    task = json.loads(task_path.read_text(encoding="utf-8").splitlines()[0])
    text = dataset_path.read_text(encoding="utf-8")

    assert dataset_path.exists()
    assert 5_800 <= estimate_tokens(text) <= 6_400
    for fact in task["required_facts"]:
        assert fact.lower() in text.lower()


def test_tool_heavy_runs_with_mock_backend(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    assert main(["benchmark", "--scenario", "tool-heavy", "--backend", "vllm", "--output", str(results)]) == 0

    assert (results / "tool_heavy_baseline.csv").exists()
    assert (results / "tool_heavy_optimized.csv").exists()
