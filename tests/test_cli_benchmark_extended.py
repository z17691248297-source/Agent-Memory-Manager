from __future__ import annotations

import csv

from agentmem.cli import main


def test_cli_benchmark_multi_stage_generates_success_and_score(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    code = main(["benchmark", "--scenario", "multi-stage", "--output", str(results)])

    assert code == 0
    rows = list(csv.DictReader((results / "multi_stage_event_sourced_memory.csv").open(encoding="utf-8")))
    assert [row["stage"] for row in rows] == ["planning", "tool_calling", "reflection", "final_answer"]
    assert all(row["success"] == "True" for row in rows)
    assert all(float(row["score"]) == 1.0 for row in rows)
    assert rows[-1]["completed_stages"] == "planning,tool_calling,reflection,final_answer"
    assert rows[-1]["memory_mode"] == "event_sourced_memory"


def test_cli_benchmark_prefix_cache_and_ablation_have_scores(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    assert main(["benchmark", "--scenario", "prefix-cache", "--output", str(results)]) == 0
    assert main(["benchmark", "--scenario", "ablation", "--output", str(results)]) == 0

    prefix_rows = list(csv.DictReader((results / "prefix_cache_optimized.csv").open(encoding="utf-8")))
    assert prefix_rows
    assert {row["unique_prefix_hashes"] for row in prefix_rows} == {"1"}
    assert all(float(row["score"]) == 1.0 for row in prefix_rows)

    ablation_rows = list(csv.DictReader((results / "ablation.csv").open(encoding="utf-8")))
    variants = {row["variant"] for row in ablation_rows}
    assert "stable_prefix_only" in variants
    assert "full_optimized" in variants
    assert all(row["success"] == "True" for row in ablation_rows)


def test_cli_benchmark_all_includes_multi_stage(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    code = main(["benchmark", "--all", "--output", str(results)])

    assert code == 0
    assert (results / "multi_stage_full_history.csv").exists()
    assert (results / "multi_stage_summary_memory.csv").exists()
    assert (results / "multi_stage_event_sourced_memory.csv").exists()
    assert (results / "multi_stage_baseline.csv").exists()
    assert (results / "multi_stage_optimized.csv").exists()
    report = (results / "report.md").read_text(encoding="utf-8")
    assert "Multi-stage 结果" in report
    assert "Success / Score" in report
