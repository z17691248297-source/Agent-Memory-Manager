from __future__ import annotations

import pytest

from agentmem.runtime.mock_llm import MockLLMClient


@pytest.fixture
def local_llm(monkeypatch):
    """Use the deterministic local LLM only inside tests."""

    def build_local_client(config_path=None):
        return MockLLMClient()

    monkeypatch.setattr("agentmem.runtime.factory.build_llm_client", build_local_client)
    monkeypatch.setattr("agentmem.benchmark.build_llm_client", build_local_client)
    return build_local_client
