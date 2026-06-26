from __future__ import annotations

import csv

from agentmem.cli import main


def test_cli_benchmark_long_session_generates_memory_modes(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    code = main(["benchmark", "--scenario", "long-session", "--output", str(results)])

    assert code == 0
    modes = ["full_history", "summary_memory", "event_sourced_memory"]
    for mode in modes:
        rows = list(csv.DictReader((results / f"long_session_{mode}.csv").open(encoding="utf-8")))
        assert len(rows) >= 50
        assert rows[-1]["memory_mode"] == mode
        assert "summary_tokens" in rows[-1]
        assert "initial_score" in rows[-1]
        assert "final_score" in rows[-1]
    assert (results / "long_session_baseline.csv").exists()
    assert (results / "long_session_optimized.csv").exists()
