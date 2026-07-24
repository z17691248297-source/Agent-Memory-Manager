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
            "cache_total_blocks": None,
            "cache_total_blocks_status": "unavailable",
            "cache_total_blocks_reason": "test_fixture",
            "cache_agent_sessions": None,
            "cache_agent_sessions_status": "unavailable",
            "cache_agent_sessions_reason": "test_fixture",
            "cache_tool_result_blocks": None,
            "cache_tool_result_blocks_status": "unavailable",
            "cache_tool_result_blocks_reason": "test_fixture",
            "cache_shared_prefix_blocks": None,
            "cache_shared_prefix_blocks_status": "unavailable",
            "cache_shared_prefix_blocks_reason": "test_fixture",
            "cache_scratchpad_blocks": None,
            "cache_scratchpad_blocks_status": "unavailable",
            "cache_scratchpad_blocks_reason": "test_fixture",
            "cache_expired_branch_blocks": None,
            "cache_expired_branch_blocks_status": "unavailable",
            "cache_expired_branch_blocks_reason": "test_fixture",
        },
    )
    return build_local_client
