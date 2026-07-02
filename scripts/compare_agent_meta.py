from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


SUMMARY_METRICS = [
    "avg_prompt_tokens",
    "avg_latency",
    "avg_ttft",
    "tokens_per_second",
    "success_rate",
    "avg_score",
]

OUTPUT_FIELDS = [
    "scenario",
    "metric",
    "off_before",
    "off_after",
    "off_delta",
    "on_before",
    "on_after",
    "on_delta",
    "delta_diff",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare AgentMem agent_meta on/off results.")
    parser.add_argument("--on", required=True, type=Path, help="results directory generated with --agent-meta on")
    parser.add_argument("--off", required=True, type=Path, help="results directory generated with --agent-meta off")
    parser.add_argument("--output", required=True, type=Path, help="comparison CSV output path")
    args = parser.parse_args()

    rows = compare(args.on, args.off)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return 0


def compare(on_dir: Path, off_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_compare_cache_stats(on_dir=on_dir, off_dir=off_dir))
    rows.extend(_compare_summary(on_dir=on_dir, off_dir=off_dir))
    return sorted(rows, key=lambda row: (str(row["scenario"]), str(row["metric"])))


def _compare_cache_stats(on_dir: Path, off_dir: Path) -> list[dict[str, Any]]:
    on_pairs = _cache_stat_pairs(on_dir)
    off_pairs = _cache_stat_pairs(off_dir)
    scenarios = sorted(set(on_pairs) | set(off_pairs))
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        on_before, on_after = on_pairs.get(scenario, ({}, {}))
        off_before, off_after = off_pairs.get(scenario, ({}, {}))
        fields = sorted(
            {
                *_numeric_fields(on_before),
                *_numeric_fields(on_after),
                *_numeric_fields(off_before),
                *_numeric_fields(off_after),
            }
        )
        for field in fields:
            off_before_value = _nested_numeric(off_before, field)
            off_after_value = _nested_numeric(off_after, field)
            on_before_value = _nested_numeric(on_before, field)
            on_after_value = _nested_numeric(on_after, field)
            off_delta = off_after_value - off_before_value
            on_delta = on_after_value - on_before_value
            rows.append(
                {
                    "scenario": scenario,
                    "metric": f"cache_stats.{field}",
                    "off_before": off_before_value,
                    "off_after": off_after_value,
                    "off_delta": off_delta,
                    "on_before": on_before_value,
                    "on_after": on_after_value,
                    "on_delta": on_delta,
                    "delta_diff": on_delta - off_delta,
                }
            )
    return rows


def _compare_summary(on_dir: Path, off_dir: Path) -> list[dict[str, Any]]:
    on_summary = _summary_by_scenario(_read_summary(on_dir))
    off_summary = _summary_by_scenario(_read_summary(off_dir))
    scenarios = sorted(set(on_summary) | set(off_summary))
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        for metric in SUMMARY_METRICS:
            off_value = float(off_summary.get(scenario, {}).get(metric, 0.0) or 0.0)
            on_value = float(on_summary.get(scenario, {}).get(metric, 0.0) or 0.0)
            rows.append(
                {
                    "scenario": scenario,
                    "metric": f"summary.{metric}",
                    "off_before": "",
                    "off_after": off_value,
                    "off_delta": "",
                    "on_before": "",
                    "on_after": on_value,
                    "on_delta": "",
                    "delta_diff": on_value - off_value,
                }
            )
    return rows


def _cache_stat_pairs(results_dir: Path) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for path in results_dir.glob("cache_stats_*_*.json"):
        parsed = _parse_cache_stats_name(path)
        if parsed is None:
            continue
        scenario, moment = parsed
        if moment not in {"before", "after"}:
            continue
        pairs.setdefault(scenario, {})[moment] = _read_json(path)
    return {
        scenario: (items.get("before", {}), items.get("after", {}))
        for scenario, items in pairs.items()
    }


def _parse_cache_stats_name(path: Path) -> tuple[str, str] | None:
    stem = path.stem
    if not stem.startswith("cache_stats_"):
        return None
    tail = stem[len("cache_stats_") :]
    if "_" not in tail:
        return None
    body, moment = tail.rsplit("_", 1)
    parts = body.split("_")
    if len(parts) >= 2 and parts[0] == "cache" and parts[1] == "pressure":
        return "cache-pressure", moment
    if len(parts) >= 2 and parts[0] == "ttl" and parts[1] == "priority":
        return "ttl-priority", moment
    if len(parts) >= 2 and parts[0] == "tool" and parts[1] == "heavy":
        return "tool-heavy", moment
    if len(parts) >= 2 and parts[0] == "long" and parts[1] == "session":
        return "long-session", moment
    if len(parts) >= 2 and parts[0] == "multi" and parts[1] == "stage":
        return "multi-stage", moment
    if len(parts) >= 2 and parts[0] == "prefix" and parts[1] == "cache":
        return "prefix-cache", moment
    return parts[0].replace("_", "-"), moment


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _numeric_fields(value: Any, prefix: str = "") -> set[str]:
    fields: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, dict):
                fields.update(_numeric_fields(item, name))
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    fields.update(_numeric_fields(child, f"{name}.{index}"))
            elif _is_number(item):
                fields.add(name)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            fields.update(_numeric_fields(item, f"{prefix}.{index}" if prefix else str(index)))
    return fields


def _nested_numeric(value: dict[str, Any], dotted: str) -> float:
    current: Any = value
    for part in dotted.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return 0.0
        else:
            return 0.0
    return _to_float(current, 0.0) or 0.0


def _read_summary(results_dir: Path) -> list[dict[str, str]]:
    path = results_dir / "summary.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _summary_by_scenario(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        scenario = str(row.get("scenario") or row.get("file") or "").strip()
        if scenario:
            grouped.setdefault(scenario, []).append(row)
    return {
        scenario: {metric: _average_metric(scenario_rows, metric) for metric in SUMMARY_METRICS}
        for scenario, scenario_rows in grouped.items()
    }


def _average_metric(rows: list[dict[str, str]], metric: str) -> float:
    values = [_to_float(row.get(metric), None) for row in rows]
    numeric = [value for value in values if value is not None]
    return sum(numeric) / len(numeric) if numeric else 0.0


def _is_number(value: Any) -> bool:
    return _to_float(value, None) is not None and not isinstance(value, bool)


def _to_float(value: Any, default: float | None = 0.0) -> float | None:
    if value in {None, ""}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())
