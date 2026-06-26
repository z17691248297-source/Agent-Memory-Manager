from __future__ import annotations

import csv

from agentmem.cli import main


def test_cli_benchmark_tool_heavy_generates_csv(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    code = main(["benchmark", "--scenario", "tool-heavy", "--output", str(results)])

    assert code == 0
    baseline = results / "tool_heavy_baseline.csv"
    optimized = results / "tool_heavy_optimized.csv"
    assert baseline.exists()
    assert optimized.exists()

    baseline_rows = list(csv.DictReader(baseline.open(encoding="utf-8")))
    optimized_rows = list(csv.DictReader(optimized.open(encoding="utf-8")))
    assert baseline_rows
    assert optimized_rows
    assert baseline_rows[0]["scenario"] == "tool-heavy"
    assert optimized_rows[0]["mode"] == "optimized"
    assert "raw_tool_tokens" in optimized_rows[0]
    assert "injected_tool_tokens" in optimized_rows[0]
