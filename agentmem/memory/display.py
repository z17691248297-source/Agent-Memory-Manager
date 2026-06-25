from __future__ import annotations

from agentmem.tools.result import ToolResult


def prompt_display_text(result: ToolResult) -> str:
    """Return the tool output that is allowed to enter prompts/display surfaces."""

    raw = result.raw_result or ""
    max_chars = _metadata_int(result.metadata, "display_max_output_chars")
    if max_chars <= 0 or len(raw) <= max_chars:
        return raw
    suffix = (
        "\n[tool output truncated for prompt/display; "
        f"raw_path={result.raw_path or 'unavailable'}; result_id={result.result_id}]"
    )
    return raw[:max_chars] + suffix


def prompt_display_tokens(result: ToolResult, estimate_tokens) -> int:
    return estimate_tokens(prompt_display_text(result))


def _metadata_int(metadata: dict, key: str) -> int:
    try:
        return int(metadata.get(key) or 0)
    except (TypeError, ValueError):
        return 0
