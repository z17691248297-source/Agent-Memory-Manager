from __future__ import annotations

import pytest

from agentmem.runtime.local_llm import LocalDeterministicLLMClient


@pytest.fixture
def local_llm(monkeypatch):
    """Use the deterministic local LLM only inside tests."""

    def build_local_client(config_path=None):
        return LocalDeterministicLLMClient()

    monkeypatch.setenv("AGENTMEM_EXTRACTOR_ENABLED", "false")
    monkeypatch.setenv("AGENTMEM_ENABLE_AGENT_META", "false")
    monkeypatch.setattr("agentmem.runtime.factory.build_llm_client", build_local_client)
    monkeypatch.setattr("agentmem.benchmark.build_llm_client", build_local_client)
    monkeypatch.setattr(
        "agentmem.benchmark.CacheStatsCollector.fetch",
        lambda self: {
            "available": False,
            "unavailable_reason": "test_fixture",
            "cache_total_blocks": -1,
            "cache_agent_sessions": -1,
            "cache_tool_result_blocks": -1,
            "cache_shared_prefix_blocks": -1,
            "cache_scratchpad_blocks": -1,
            "cache_expired_branch_blocks": -1,
        },
    )
    return build_local_client
