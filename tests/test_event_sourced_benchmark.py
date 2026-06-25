from __future__ import annotations

import csv

from agentmem.cli import main


def test_long_session_event_sourced_benchmark_generates_csv_and_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTMEM_LLM_BACKEND", "mock")
    results = tmp_path / "results"

    assert main(["benchmark", "--scenario", "long-session", "--backend", "mock", "--output", str(results)]) == 0
    assert (results / "long_session_full_history.csv").exists()
    assert (results / "long_session_summary_memory.csv").exists()
    assert (results / "long_session_event_sourced_memory.csv").exists()
    assert (results / "event_log").exists()
    assert (results / "event_memory_snapshots").exists()

    rows = list(csv.DictReader((results / "long_session_event_sourced_memory.csv").open(encoding="utf-8")))
    assert rows
    assert rows[-1]["memory_mode"] == "event_sourced_memory"
    assert int(float(rows[-1]["event_count"])) > 0
    assert "state_view_tokens" in rows[-1]
    assert "memory_delta_count" in rows[-1]
    assert "fact_count" in rows[-1]
    assert "artifact_ref_count" in rows[-1]
    assert "initial_score" in rows[-1]
    assert "final_score" in rows[-1]

    assert main(["report", "--results-dir", str(results)]) == 0
    report = (results / "report.md").read_text(encoding="utf-8")
    assert "## Event-Sourced Agent Memory" in report


def test_multi_stage_event_sourced_benchmark_generates_csv(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTMEM_LLM_BACKEND", "mock")
    results = tmp_path / "results"

    assert main(["benchmark", "--scenario", "multi-stage", "--backend", "mock", "--output", str(results)]) == 0

    assert (results / "multi_stage_full_history.csv").exists()
    assert (results / "multi_stage_summary_memory.csv").exists()
    assert (results / "multi_stage_event_sourced_memory.csv").exists()
    rows = list(csv.DictReader((results / "multi_stage_event_sourced_memory.csv").open(encoding="utf-8")))
    assert [row["stage"] for row in rows] == ["planning", "tool_calling", "reflection", "final_answer"]
    assert all("missing_keywords" in row for row in rows)
