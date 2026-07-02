from __future__ import annotations

import argparse
import csv
from pathlib import Path


OUTPUT_FIELDS = [
    "results_dir",
    "scenario",
    "mode",
    "agent_meta_enabled",
    "avg_prompt_tokens",
    "avg_latency",
    "avg_ttft",
    "success_rate",
    "avg_score",
    "avg_raw_tool_tokens",
    "avg_injected_tool_tokens",
    "avg_tool_compression_ratio",
    "avg_branch_saving_ratio",
    "cache_stats_available",
    "agent_id",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect final AgentMem summary.csv files into one CSV.")
    parser.add_argument("--inputs", nargs="+", required=True, type=Path, help="results directories containing summary.csv")
    parser.add_argument("--output", required=True, type=Path, help="combined summary CSV output path")
    args = parser.parse_args()

    rows = collect_final_results(args.inputs)
    write_summary(args.output, rows)
    return 0


def collect_final_results(results_dirs: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for results_dir in results_dirs:
        summary_path = results_dir / "summary.csv"
        if not summary_path.exists():
            continue
        rows.extend(_read_summary_rows(results_dir, summary_path))
    return _dedupe_rows(rows)


def write_summary(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_summary_rows(results_dir: Path, summary_path: Path) -> list[dict[str, str]]:
    with summary_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return [_normalize_row(results_dir, row) for row in reader]


def _normalize_row(results_dir: Path, row: dict[str, str | None]) -> dict[str, str]:
    normalized = {field: "" for field in OUTPUT_FIELDS}
    normalized["results_dir"] = str(results_dir)
    for field in OUTPUT_FIELDS:
        if field == "results_dir":
            continue
        value = row.get(field)
        normalized[field] = "" if value is None else str(value)
    return normalized


def _dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        key = tuple(row.get(field, "") for field in OUTPUT_FIELDS)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


if __name__ == "__main__":
    raise SystemExit(main())
