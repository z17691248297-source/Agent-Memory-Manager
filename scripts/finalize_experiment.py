#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmem.experiment import utc_timestamp, write_manifest
from agentmem.metrics.validation import validate_results_dir, write_validation


CACHE_VALUE_COLUMNS = [
    "cache_total_blocks",
    "cache_agent_sessions",
    "cache_tool_result_blocks",
    "cache_shared_prefix_blocks",
    "cache_scratchpad_blocks",
    "cache_expired_branch_blocks",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize an AgentMem experiment directory.")
    parser.add_argument("experiment_dir", help="results/<experiment_id> directory")
    parser.add_argument("--cache-max-age-seconds", type=float, default=300)
    args = parser.parse_args()

    root = Path(args.experiment_dir)
    raw = root / "raw"
    stale_reason = _sanitize_stale_cache_json(raw, max_age_seconds=args.cache_max_age_seconds)
    if stale_reason:
        _sanitize_cache_columns(raw, stale_reason)

    result = validate_results_dir(raw)
    write_validation(root / "validation.json", result)
    _update_manifest(root, result.valid, stale_reason)
    return 0 if result.valid else 1


def _sanitize_stale_cache_json(raw_dir: Path, *, max_age_seconds: float) -> str:
    stale_reasons: list[str] = []
    for path in sorted(raw_dir.rglob("cache_stats_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        generated_at = _latest_generated_at(payload.get("raw", payload))
        if generated_at is None:
            continue
        age = time.time() - generated_at
        if age <= max_age_seconds:
            continue
        reason = f"stale_cache_stats: age_seconds={age:.0f}, max_age_seconds={max_age_seconds:.0f}"
        stale_reasons.append(reason)
        _mark_cache_payload_unavailable(payload, reason)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not stale_reasons:
        return ""
    return sorted(stale_reasons, key=len)[0]


def _mark_cache_payload_unavailable(payload: dict[str, Any], reason: str) -> None:
    payload["available"] = False
    payload["unavailable_reason"] = reason
    for column in CACHE_VALUE_COLUMNS:
        payload[column] = None
        payload[f"{column}_status"] = "unavailable"
        payload[f"{column}_reason"] = reason


def _sanitize_cache_columns(raw_dir: Path, reason: str) -> None:
    for path in sorted(raw_dir.rglob("*.csv")):
        if path.name == "summary.csv":
            continue
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
            fieldnames = list(reader.fieldnames or [])
        if not rows or "cache_stats_available" not in fieldnames:
            continue
        for row in rows:
            row["cache_stats_available"] = "False"
            row["cache_stats_unavailable_reason"] = reason
            if "cache_stats_scope" in row:
                row["cache_stats_scope"] = "global"
            for column in CACHE_VALUE_COLUMNS:
                if column in row:
                    row[column] = ""
                status_column = f"{column}_status"
                reason_column = f"{column}_reason"
                if status_column in row:
                    row[status_column] = "unavailable"
                if reason_column in row:
                    row[reason_column] = reason
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def _latest_generated_at(value: Any) -> float | None:
    latest: float | None = None
    if isinstance(value, dict):
        raw = value.get("generated_at") or value.get("timestamp_unix")
        if isinstance(raw, (int, float)):
            latest = float(raw)
        for item in value.values():
            candidate = _latest_generated_at(item)
            if candidate is not None:
                latest = candidate if latest is None else max(latest, candidate)
    elif isinstance(value, list):
        for item in value:
            candidate = _latest_generated_at(item)
            if candidate is not None:
                latest = candidate if latest is None else max(latest, candidate)
    return latest


def _update_manifest(root: Path, validation_passed: bool, stale_reason: str) -> None:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["end_time"] = utc_timestamp()
    manifest["validation_passed"] = validation_passed
    if stale_reason:
        manifest["real_gpu_metrics"] = False
        manifest["cache_stats_note"] = f"cache stats endpoint returned stale data; metrics marked unavailable: {stale_reason}"
    write_manifest(manifest_path, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
