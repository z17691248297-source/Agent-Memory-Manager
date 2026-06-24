from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


FIELDS = [
    "run_id",
    "round",
    "mode",
    "experiment",
    "stage",
    "prompt_tokens",
    "system_tokens",
    "tool_schema_tokens",
    "tool_brief_tokens",
    "loaded_skill_tokens",
    "loaded_skill_names",
    "tool_names",
    "route_reason",
    "history_tokens",
    "summary_tokens",
    "tool_summary_tokens",
    "branch_tokens",
    "raw_tool_tokens",
    "injected_tool_tokens",
    "tool_compression_ratio",
    "latency",
    "ttft",
    "output_tokens",
    "total_tokens",
    "tokens_per_second",
    "peak_gpu_memory_mb",
    "success",
]


class MetricsCollector:
    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.rows: list[dict[str, Any]] = []

    def record(self, row: dict[str, Any]) -> None:
        normalized = {field: row.get(field, "") for field in FIELDS}
        self.rows.append(normalized)

    def write_csv(self) -> Path:
        with self.output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)
        return self.output_path
