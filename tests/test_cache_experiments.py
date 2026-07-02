from __future__ import annotations

import csv
import json

from agentmem.cli import main


def test_cache_pressure_benchmark_writes_segments_and_memory_plan(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    code = main(["benchmark", "--scenario", "cache-pressure", "--sessions", "2", "--agent-id", "test_agent", "--output", str(results)])

    assert code == 0
    rows = list(csv.DictReader((results / "cache_pressure.csv").open(encoding="utf-8")))
    assert len(rows) == 10
    assert {row["session_id"] for row in rows} == {"cache_pressure_session_1", "cache_pressure_session_2"}
    assert {row["segment_type"] for row in rows} == {
        "shared_prefix",
        "tool_schema",
        "tool_result",
        "scratchpad",
        "expired_branch",
    }
    assert (results / "cache_stats_cache_pressure_sessions_2_before.json").exists()
    assert (results / "cache_stats_cache_pressure_sessions_2_after.json").exists()
    plan_files = sorted((results / "memory_plan").glob("cache_pressure_session_*.jsonl"))
    assert len(plan_files) == 2
    first_plan = json.loads(plan_files[0].read_text(encoding="utf-8").splitlines()[0])
    assert rows[0]["agent_id"] == "test_agent"
    assert first_plan["agent_id"] in {"", "test_agent"}
    assert first_plan["run_id"].startswith("cache_pressure_session_")
    assert first_plan["segment_type"] in {"shared_prefix", "tool_schema", "tool_result", "scratchpad", "expired_branch"}
    assert "agent_meta" in first_plan


def test_ttl_priority_benchmark_writes_expected_policy(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    code = main(["benchmark", "--scenario", "ttl-priority", "--output", str(results)])

    assert code == 0
    rows = list(csv.DictReader((results / "ttl_priority.csv").open(encoding="utf-8")))
    policy = {(row["segment_type"], row["priority"], row["ttl"]) for row in rows}
    assert rows[0]["agent_id"].startswith("agentmem_ttl_priority_config_")
    assert ("shared_prefix", "high", "3600") in policy
    assert ("tool_schema", "high", "1800") in policy
    assert ("tool_result", "low", "120") in policy
    assert ("scratchpad", "low", "60") in policy
    assert ("expired_branch", "drop", "1") in policy
    assert (results / "summary.csv").exists()
    summary_rows = list(csv.DictReader((results / "summary.csv").open(encoding="utf-8")))
    assert "tokens_per_second" in summary_rows[0]
