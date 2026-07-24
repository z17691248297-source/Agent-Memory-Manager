from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from agentmem.tools.path_policy import PROJECT_ROOT, resolve_allowed_path

ALLOWED_ROOT = PROJECT_ROOT / "benchmarks" / "fixtures"


def analyze_csv(input_text: str, context: dict | None = None) -> str:
    path = _extract_csv_path(input_text)
    if path:
        target = resolve_allowed_path(path, [ALLOWED_ROOT])
        text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else _mock_csv()
    else:
        text = _mock_csv()
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    columns = reader.fieldnames or []
    numeric_stats: list[str] = []
    for col in columns:
        values: list[float] = []
        for row in rows:
            try:
                values.append(float(row.get(col, "")))
            except ValueError:
                pass
        if values:
            numeric_stats.append(f"{col}: count={len(values)}, mean={sum(values) / len(values):.2f}")
    return "\n".join(
        [
            "CSV 分析结果:",
            f"行数: {len(rows)}",
            f"列数: {len(columns)}",
            f"列名: {columns}",
            "数值列统计:",
            *numeric_stats,
            "原始 CSV 片段:",
            text[:4000],
        ]
    )


def _extract_csv_path(text: str) -> str | None:
    match = re.search(r"([\w./-]+\.csv)", text)
    return match.group(1) if match else None


def _mock_csv() -> str:
    lines = ["id,latency_ms,prompt_tokens,success"]
    for idx in range(300):
        lines.append(f"{idx},{80 + idx % 40},{900 + idx % 500},{idx % 7 != 0}")
    return "\n".join(lines)
