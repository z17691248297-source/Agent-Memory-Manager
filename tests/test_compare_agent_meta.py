from __future__ import annotations

import csv
import json

from scripts.compare_agent_meta import compare


def test_compare_agent_meta_outputs_metric_deltas(tmp_path) -> None:
    on_dir = tmp_path / "on"
    off_dir = tmp_path / "off"
    on_dir.mkdir()
    off_dir.mkdir()
    fields = [
        "scenario",
        "avg_prompt_tokens",
        "avg_latency",
        "avg_ttft",
        "tokens_per_second",
        "success_rate",
        "avg_score",
        "cache_total_blocks",
        "cache_agent_sessions",
        "cache_tool_result_blocks",
        "cache_shared_prefix_blocks",
        "cache_scratchpad_blocks",
        "cache_expired_branch_blocks",
    ]
    _write_summary(off_dir / "summary.csv", fields, {"scenario": "cache-pressure", "avg_prompt_tokens": "100", "tokens_per_second": "10"})
    _write_summary(on_dir / "summary.csv", fields, {"scenario": "cache-pressure", "avg_prompt_tokens": "80", "tokens_per_second": "12"})
    _write_json(off_dir / "cache_stats_cache_pressure_sessions_2_before.json", {"cache_total_blocks": 10, "segments": {"expired_branch": {"cached_blocks": 1}}})
    _write_json(off_dir / "cache_stats_cache_pressure_sessions_2_after.json", {"cache_total_blocks": 15, "segments": {"expired_branch": {"cached_blocks": 4}}})
    _write_json(on_dir / "cache_stats_cache_pressure_sessions_2_before.json", {"cache_total_blocks": 20, "segments": {"expired_branch": {"cached_blocks": 2}}})
    _write_json(on_dir / "cache_stats_cache_pressure_sessions_2_after.json", {"cache_total_blocks": 23, "segments": {"expired_branch": {"cached_blocks": 3}}})

    rows = compare(on_dir, off_dir)

    prompt_row = next(row for row in rows if row["scenario"] == "cache-pressure" and row["metric"] == "summary.avg_prompt_tokens")
    tps_row = next(row for row in rows if row["scenario"] == "cache-pressure" and row["metric"] == "summary.tokens_per_second")
    cache_row = next(row for row in rows if row["scenario"] == "cache-pressure" and row["metric"] == "cache_stats.cache_total_blocks")
    expired_row = next(
        row for row in rows if row["scenario"] == "cache-pressure" and row["metric"] == "cache_stats.segments.expired_branch.cached_blocks"
    )
    assert prompt_row["off_after"] == 100
    assert prompt_row["on_after"] == 80
    assert prompt_row["delta_diff"] == -20
    assert tps_row["delta_diff"] == 2
    assert cache_row["off_delta"] == 5
    assert cache_row["on_delta"] == 3
    assert cache_row["delta_diff"] == -2
    assert expired_row["off_delta"] == 3
    assert expired_row["on_delta"] == 1


def _write_summary(path, fields, row) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerow({field: row.get(field, "0") for field in fields})


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
