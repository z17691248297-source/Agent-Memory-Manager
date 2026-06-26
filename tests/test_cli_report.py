from __future__ import annotations

from agentmem.cli import main


def test_cli_report_generates_markdown(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    assert main(["benchmark", "--scenario", "tool-heavy", "--output", str(results)]) == 0
    assert main(["report", "--results-dir", str(results)]) == 0

    report = results / "report.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "# AgentMem Benchmark Report" in text
    assert "## 4. Workloads" in text
    assert "## 6. Success / Score" in text
    assert "## 7. Tool-heavy 结果" in text
    assert "## Configured Model Backend Results" in text
