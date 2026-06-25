from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any


LOG_KEYWORDS = [
    "KV cache allocation failed",
    "CUDA OOM",
    "timeout",
    "KV cache",
    "OOM",
    "exception",
    "failed",
]

SEVERITIES = ["ERROR", "WARNING", "WARN", "INFO", "DEBUG", "TRACE"]


def analyze_log_text(text: str, max_samples_per_group: int = 3) -> dict[str, Any]:
    lines = text.splitlines()
    severity_counts: Counter[str] = Counter()
    groups: dict[str, dict[str, Any]] = {}

    for line_number, line in enumerate(lines, start=1):
        severity = _severity(line)
        severity_counts[severity] += 1
        matched = matched_keywords(line)
        if not matched and severity not in {"ERROR", "WARN", "WARNING"}:
            continue
        signature = log_signature(line, matched)
        group = groups.setdefault(
            signature,
            {
                "signature": signature,
                "count": 0,
                "first_line": line_number,
                "last_line": line_number,
                "sample": [],
                "keywords": [],
                "severity": severity,
            },
        )
        group["count"] += 1
        group["last_line"] = line_number
        group["keywords"] = _dedupe([*group["keywords"], *matched])
        if len(group["sample"]) < max_samples_per_group:
            group["sample"].append(line[:500])

    error_groups = sorted(groups.values(), key=lambda item: (item["count"], len(item["keywords"])), reverse=True)
    return {
        "total_lines": len(lines),
        "severity_counts": dict(severity_counts),
        "error_groups": error_groups,
        "root_cause_candidates": root_cause_candidates(error_groups),
    }


def format_log_summary(text: str) -> str:
    return json.dumps(analyze_log_text(text), ensure_ascii=False, indent=2)


def matched_keywords(text: str) -> list[str]:
    lowered = text.lower()
    return _dedupe([keyword for keyword in LOG_KEYWORDS if keyword.lower() in lowered])


def log_signature(line: str, keywords: list[str] | None = None) -> str:
    keywords = keywords or matched_keywords(line)
    if keywords:
        return " + ".join(keywords)
    cleaned = re.sub(r"\b\d+\b", "<n>", line)
    cleaned = re.sub(r"0x[0-9a-fA-F]+", "<hex>", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for severity in SEVERITIES:
        cleaned = re.sub(rf"\b{severity}\b", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned[:120] or "log_line"


def root_cause_candidates(error_groups: list[dict[str, Any]]) -> list[str]:
    candidates: list[str] = []
    priority = [
        "KV cache allocation failed",
        "CUDA OOM",
        "OOM",
        "timeout",
        "KV cache",
        "exception",
        "failed",
    ]
    for keyword in priority:
        for group in error_groups:
            if keyword in group.get("keywords", []):
                candidates.append(f"{keyword}: {group['signature']} count={group['count']}")
                break
    return _dedupe(candidates)[:6]


def _severity(line: str) -> str:
    for severity in SEVERITIES:
        if re.search(rf"\b{severity}\b", line, flags=re.IGNORECASE):
            return "WARN" if severity == "WARNING" else severity
    return "INFO"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
