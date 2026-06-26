from __future__ import annotations

from pathlib import Path


def test_openeuler_deployment_doc_exists() -> None:
    path = Path("docs/openeuler_deployment.md")

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "openEuler 22.03 LTS" in text
    assert "openKylin" in text
    assert "python -m agentmem benchmark --scenario tool-heavy" in text
