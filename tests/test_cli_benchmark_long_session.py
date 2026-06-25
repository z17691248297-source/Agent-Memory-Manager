from __future__ import annotations

import csv

from agentmem.cli import main


def test_cli_benchmark_long_session_mock_generates_four_memory_modes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTMEM_LLM_BACKEND", "mock")
    results = tmp_path / "results"

    code = main(["benchmark", "--scenario", "long-session", "--backend", "mock", "--output", str(results)])

    assert code == 0
    modes = ["full_history", "summary_memory", "event_sourced_memory"]
    for mode in modes:
        rows = list(csv.DictReader((results / f"long_session_{mode}.csv").open(encoding="utf-8")))
        assert len(rows) >= 50
        assert rows[-1]["memory_mode"] == mode
        assert "summary_tokens" in rows[-1]
        assert "initial_score" in rows[-1]
        assert "final_score" in rows[-1]
