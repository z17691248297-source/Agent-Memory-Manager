from __future__ import annotations

from agentmem.cli import main


def test_report_contains_os_environment_and_extractor_fields(tmp_path, local_llm) -> None:
    results = tmp_path / "results"

    assert main(["benchmark", "--scenario", "tool-heavy", "--output", str(results)]) == 0
    assert main(["report", "--results-dir", str(results)]) == 0

    text = (results / "report.md").read_text(encoding="utf-8")
    assert "client_os" in text
    assert "client_environment" in text
    assert "model_server_os" in text
    assert "main_llm_backend" in text
    assert "extractor_backend" in text
