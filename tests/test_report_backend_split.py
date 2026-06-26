from __future__ import annotations

from agentmem.cli import main


def test_report_uses_configured_model_backend_section(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    assert main(["benchmark", "--scenario", "tool-heavy", "--output", str(results)]) == 0
    assert main(["report", "--results-dir", str(results)]) == 0

    text = (results / "report.md").read_text(encoding="utf-8")
    assert "## Configured Model Backend Results" in text
    assert "Mock Backend Results" not in text
    assert "vLLM Backend Results" not in text
    assert "mock backend" not in text.lower()
