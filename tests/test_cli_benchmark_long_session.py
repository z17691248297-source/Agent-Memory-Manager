from __future__ import annotations

import csv

from agentmem.cli import main


def test_cli_benchmark_long_session_mock_generates_both_modes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTMEM_LLM_BACKEND", "mock")
    results = tmp_path / "results"

    code = main(["benchmark", "--scenario", "long-session", "--backend", "mock", "--output", str(results)])

    assert code == 0
    baseline_rows = list(csv.DictReader((results / "long_session_baseline.csv").open(encoding="utf-8")))
    optimized_rows = list(csv.DictReader((results / "long_session_optimized.csv").open(encoding="utf-8")))
    assert len(baseline_rows) >= 50
    assert len(optimized_rows) >= 50
    assert baseline_rows[-1]["mode"] == "baseline"
    assert optimized_rows[-1]["mode"] == "optimized"
    assert "summary_tokens" in optimized_rows[-1]
