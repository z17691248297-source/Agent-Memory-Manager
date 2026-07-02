from __future__ import annotations

import csv

from scripts.collect_final_results import OUTPUT_FIELDS, collect_final_results, write_summary


def test_collect_final_results_adds_results_dir_and_preserves_fields(tmp_path) -> None:
    first = tmp_path / "results_tool_heavy_final"
    second = tmp_path / "results_cache_pressure_on_final"
    first.mkdir()
    second.mkdir()
    _write_summary(
        first / "summary.csv",
        [
            "scenario",
            "mode",
            "agent_meta_enabled",
            "avg_prompt_tokens",
            "avg_latency",
            "avg_ttft",
            "success_rate",
            "avg_score",
            "avg_raw_tool_tokens",
            "avg_injected_tool_tokens",
            "avg_tool_compression_ratio",
            "avg_branch_saving_ratio",
            "cache_stats_available",
            "agent_id",
        ],
        {
            "scenario": "tool-heavy",
            "mode": "agent-meta-on",
            "agent_meta_enabled": "True",
            "avg_prompt_tokens": "1200",
            "avg_latency": "1.2",
            "avg_ttft": "0.2",
            "success_rate": "1.0",
            "avg_score": "0.9",
            "avg_raw_tool_tokens": "800",
            "avg_injected_tool_tokens": "240",
            "avg_tool_compression_ratio": "0.3",
            "avg_branch_saving_ratio": "0.0",
            "cache_stats_available": "True",
            "agent_id": "agentmem_tool_heavy_on_123",
        },
    )
    _write_summary(
        second / "summary.csv",
        ["scenario", "agent_meta_enabled", "avg_latency", "agent_id"],
        {
            "scenario": "cache-pressure",
            "agent_meta_enabled": "False",
            "avg_latency": "2.4",
            "agent_id": "agentmem_cache_pressure_off_456",
        },
    )

    rows = collect_final_results([first, second])

    assert len(rows) == 2
    assert rows[0]["results_dir"] == str(first)
    assert rows[0]["scenario"] == "tool-heavy"
    assert rows[0]["avg_tool_compression_ratio"] == "0.3"
    assert rows[1]["results_dir"] == str(second)
    assert rows[1]["scenario"] == "cache-pressure"
    assert rows[1]["mode"] == ""
    assert rows[1]["avg_prompt_tokens"] == ""
    assert rows[1]["cache_stats_available"] == ""
    assert set(rows[1]) == set(OUTPUT_FIELDS)


def test_collect_final_results_writes_output_and_skips_missing_summary(tmp_path) -> None:
    existing = tmp_path / "results_ttl_priority_on_final"
    missing = tmp_path / "results_branching_final"
    output = tmp_path / "final_summary.csv"
    existing.mkdir()
    missing.mkdir()
    _write_summary(existing / "summary.csv", ["scenario", "agent_id"], {"scenario": "ttl-priority", "agent_id": "agentmem_ttl"})

    rows = collect_final_results([existing, missing])
    write_summary(output, rows)

    with output.open("r", encoding="utf-8", newline="") as file:
        written = list(csv.DictReader(file))
    assert len(written) == 1
    assert written[0]["results_dir"] == str(existing)
    assert written[0]["scenario"] == "ttl-priority"
    assert written[0]["agent_id"] == "agentmem_ttl"
    assert written[0]["avg_score"] == ""


def _write_summary(path, fields, row) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})
