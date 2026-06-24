from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompressionResult:
    summary: str
    recent_messages: list[dict[str, str]]


class ContextCompressor:
    """规则版历史压缩器：保留最近 N 轮，旧历史压缩成 summary。"""

    def compress(
        self,
        messages: list[dict[str, str]],
        recent_rounds: int = 3,
    ) -> CompressionResult:
        if recent_rounds <= 0:
            recent_count = 0
        else:
            recent_count = recent_rounds * 2
        recent_messages = messages[-recent_count:] if recent_count else []
        old_messages = messages[:-recent_count] if recent_count else messages

        anchors: list[str] = []
        summary_lines: list[str] = []
        for item in old_messages:
            role = item.get("role", "")
            content = item.get("content", "").strip()
            if not content:
                continue
            if role == "tool":
                result_id = item.get("result_id") or _extract_result_id(content)
                summary_lines.append(f"工具结果: {result_id or 'unknown'}，原文已外置。")
            else:
                line = f"{role}: {_compact_line(content)}"
                if _is_anchor(content):
                    anchors.append(line)
                summary_lines.append(line)
        summary = "\n".join(_dedupe([*anchors, *summary_lines[-20:]]))
        return CompressionResult(summary=summary, recent_messages=recent_messages)


def _compact_line(text: str, max_chars: int = 160) -> str:
    single = " ".join(text.split())
    if len(single) <= max_chars:
        return single
    return single[:max_chars] + "..."


def _extract_result_id(text: str) -> str | None:
    for line in text.splitlines():
        if "result_id" in line:
            return line.split(":", 1)[-1].strip()
    return None


def _is_anchor(text: str) -> bool:
    """Preserve explicit long-session constraints before recency trimming."""
    lowered = text.lower()
    return any(marker in lowered for marker in ["关键约束", "constraint_", "must remember"])


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            output.append(line)
    return output
