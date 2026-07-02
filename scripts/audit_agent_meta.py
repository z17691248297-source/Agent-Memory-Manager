from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Any


FIELDS = ["results_dir", "rows", "agent_meta_sent_true", "agent_meta_sent_false", "empty_segment_rows", "segment_type_distribution"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit AgentMem result CSVs for agent_meta client-side behavior.")
    parser.add_argument("results_dir", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    rows = [audit_results_dir(path) for path in args.results_dir]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(__import__("sys").stdout, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return 0


def audit_results_dir(results_dir: Path) -> dict[str, Any]:
    rows = _read_result_rows(results_dir)
    segments = Counter(str(row.get("agent_meta_segment_type") or "") for row in rows)
    return {
        "results_dir": str(results_dir),
        "rows": len(rows),
        "agent_meta_sent_true": sum(1 for row in rows if _to_bool(row.get("agent_meta_sent"))),
        "agent_meta_sent_false": sum(1 for row in rows if not _to_bool(row.get("agent_meta_sent"))),
        "empty_segment_rows": segments.get("", 0),
        "segment_type_distribution": ";".join(f"{key or '<empty>'}:{value}" for key, value in sorted(segments.items())),
    }


def _read_result_rows(results_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(results_dir.glob("*.csv")):
        if path.name in {"summary.csv", "vllm_benchmark.csv"}:
            continue
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            if "agent_meta_sent" not in (reader.fieldnames or []):
                continue
            rows.extend(reader)
    return rows


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
