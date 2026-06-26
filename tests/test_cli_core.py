from __future__ import annotations

import csv
import json

from agentmem.cli import main


def test_direct_prompt_shorthand_runs_tool(tmp_path, capsys, local_llm) -> None:
    code = main(
        [
            "--stage",
            "tool_calling",
            "--results-dir",
            str(tmp_path / "results"),
            "请计算 1 + 2。",
        ]
    )

    assert code == 0
    output = capsys.readouterr().out
    assert "tool_names: calculator" in output
    assert "prompt_tokens:" in output


def test_eval_writes_metrics_csv(tmp_path, local_llm) -> None:
    workload = tmp_path / "workload.jsonl"
    workload.write_text(
        '{"input": "请计算 1 + 2。", "stage": "tool_calling", "expected_tools": ["calculator"]}\n',
        encoding="utf-8",
    )
    output = tmp_path / "metrics.csv"

    code = main(
        [
            "eval",
            "--workload",
            str(workload),
            "--output",
            str(output),
            "--results-dir",
            str(tmp_path / "results"),
        ]
    )

    assert code == 0
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["tool_names"] == "calculator"


def test_tools_and_results_commands(tmp_path, capsys, local_llm) -> None:
    assert main(["tools", "--json"]) == 0
    tools = json.loads(capsys.readouterr().out)
    assert any(tool["name"] == "calculator" for tool in tools)

    results_dir = tmp_path / "results"
    assert main(["run", "请计算 1 + 2。", "--stage", "tool_calling", "--results-dir", str(results_dir)]) == 0
    capsys.readouterr()
    assert main(["results", "--results-dir", str(results_dir), "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["tool_results"] >= 1


def test_clean_preserves_audit_report(tmp_path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    audit = results_dir / "audit_report.md"
    report = results_dir / "report.md"
    audit.write_text("audit", encoding="utf-8")
    report.write_text("generated", encoding="utf-8")

    assert main(["clean", "--results-dir", str(results_dir)]) == 0

    assert audit.exists()
    assert not report.exists()
