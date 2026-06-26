from __future__ import annotations

import csv

from agentmem.cli import main


def test_cli_benchmark_branching_has_saving_ratio(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    code = main(["benchmark", "--scenario", "branching", "--output", str(results)])

    assert code == 0
    rows = list(csv.DictReader((results / "branch_benchmark.csv").open(encoding="utf-8")))
    assert rows
    assert "branch_saving_ratio" in rows[0]
    optimized = [row for row in rows if row["mode"] == "optimized"]
    assert optimized
    assert float(optimized[-1]["branch_saving_ratio"]) > 0
