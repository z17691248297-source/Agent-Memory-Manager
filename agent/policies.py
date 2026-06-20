from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextPolicy:
    name: str
    token_budget: int
    recent_message_limit: int
    inline_tool_results: bool
    externalize_tool_results: bool
    tool_result_inline_token_limit: int
    use_summary: bool
    use_importance_selection: bool
    stable_prefix: bool


BASELINE_POLICY = ContextPolicy(
    name="baseline",
    token_budget=100_000,
    recent_message_limit=10_000,
    inline_tool_results=True,
    externalize_tool_results=False,
    tool_result_inline_token_limit=100_000,
    use_summary=False,
    use_importance_selection=False,
    stable_prefix=False,
)


OPTIMIZED_POLICY = ContextPolicy(
    name="context_compiler",
    token_budget=4096,
    recent_message_limit=8,
    inline_tool_results=False,
    externalize_tool_results=True,
    tool_result_inline_token_limit=220,
    use_summary=True,
    use_importance_selection=True,
    stable_prefix=True,
)


RECENT_WINDOW_POLICY = ContextPolicy(
    name="recent_window",
    token_budget=4096,
    recent_message_limit=8,
    inline_tool_results=True,
    externalize_tool_results=False,
    tool_result_inline_token_limit=100_000,
    use_summary=False,
    use_importance_selection=False,
    stable_prefix=True,
)


SUMMARY_ARTIFACT_POLICY = ContextPolicy(
    name="summary_artifact",
    token_budget=4096,
    recent_message_limit=8,
    inline_tool_results=False,
    externalize_tool_results=True,
    tool_result_inline_token_limit=220,
    use_summary=True,
    use_importance_selection=False,
    stable_prefix=True,
)


POLICIES = {
    BASELINE_POLICY.name: BASELINE_POLICY,
    RECENT_WINDOW_POLICY.name: RECENT_WINDOW_POLICY,
    SUMMARY_ARTIFACT_POLICY.name: SUMMARY_ARTIFACT_POLICY,
    OPTIMIZED_POLICY.name: OPTIMIZED_POLICY,
}

