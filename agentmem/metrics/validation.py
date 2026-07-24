from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentmem.metrics.metric_models import descriptive_stats, parse_number


NON_NEGATIVE_COUNTERS = {
    "extractor_success_count",
    "extractor_failure_count",
    "request_count",
    "tool_call_count",
    "cache_hit_count",
    "cache_miss_count",
    "eviction_count",
    "success_count",
    "failure_count",
}

FORMAL_METRICS = [
    "prompt_tokens",
    "output_tokens",
    "total_tokens",
    "total_latency",
    "latency",
    "ttft",
    "prefill_latency",
    "decode_latency",
    "tokens_per_second",
    "tool_latency",
    "memory_projection_latency",
    "extractor_latency",
    "peak_gpu_memory_mb",
    "kv_cache_usage",
    "prefix_cache_hit_rate",
    "cached_prompt_tokens",
    "score",
]


@dataclass
class TrialIssue:
    file: str
    row_number: int
    trial_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "row_number": self.row_number,
            "trial_id": self.trial_id,
            "reason": self.reason,
        }


@dataclass
class ValidationResult:
    valid: bool
    invalid_trials: list[TrialIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "invalid_trials": [item.to_dict() for item in self.invalid_trials],
            "warnings": list(self.warnings),
            "stats": self.stats,
        }


def validate_result_rows(rows: list[dict[str, Any]], *, file_name: str = "") -> ValidationResult:
    issues: list[TrialIssue] = []
    for idx, row in enumerate(rows, start=2):
        for field_name in NON_NEGATIVE_COUNTERS:
            if field_name not in row or row.get(field_name) in {None, ""}:
                continue
            parsed = parse_number(row.get(field_name))
            if parsed is not None and parsed < 0:
                issues.append(
                    TrialIssue(
                        file=file_name,
                        row_number=idx,
                        trial_id=str(row.get("trial_id") or row.get("run_id") or ""),
                        reason=f"{field_name} is negative: {row.get(field_name)}",
                    )
                )
    valid_rows = exclude_invalid_trials(rows, issues)
    stats = [descriptive_stats(valid_rows, metric) for metric in FORMAL_METRICS if _has_column(rows, metric)]
    return ValidationResult(valid=not issues, invalid_trials=issues, stats=stats)


def validate_results_dir(results_dir: str | Path) -> ValidationResult:
    root = Path(results_dir)
    all_issues: list[TrialIssue] = []
    all_stats: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in sorted(root.glob("*.csv")):
        if path.name in {"summary.csv"}:
            continue
        rows = _read_csv(path)
        result = validate_result_rows(rows, file_name=path.name)
        all_issues.extend(result.invalid_trials)
        for stat in result.stats:
            stat["file"] = path.name
        all_stats.extend(result.stats)
        warnings.extend(result.warnings)
    return ValidationResult(valid=not all_issues, invalid_trials=all_issues, warnings=warnings, stats=all_stats)


def write_validation(path: str | Path, result: ValidationResult) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def exclude_invalid_trials(rows: list[dict[str, Any]], issues: list[TrialIssue]) -> list[dict[str, Any]]:
    invalid_keys = {(issue.file, issue.row_number) for issue in issues}
    if not invalid_keys:
        return list(rows)
    output: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=2):
        # File-specific filtering is applied by caller; this also supports direct per-file validation.
        if any(row_id == idx for _file, row_id in invalid_keys):
            continue
        output.append(row)
    return output


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _has_column(rows: list[dict[str, Any]], column: str) -> bool:
    return any(column in row for row in rows)
