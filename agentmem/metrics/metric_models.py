from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import mean, median, pstdev
from typing import Any, Literal


MetricStatus = Literal["ok", "unavailable", "invalid", "estimated"]


@dataclass(frozen=True)
class MetricValue:
    value: float | int | None
    status: MetricStatus
    source: str
    reason: str | None = None
    timestamp: str | None = None
    scope: str = "unknown"

    def to_dict(self, prefix: str) -> dict[str, Any]:
        return {
            prefix: self.value if self.value is not None else "",
            f"{prefix}_status": self.status,
            f"{prefix}_source": self.source,
            f"{prefix}_reason": self.reason or "",
            f"{prefix}_scope": self.scope,
            f"{prefix}_timestamp": self.timestamp or "",
        }

    def as_plain_dict(self) -> dict[str, Any]:
        return asdict(self)


def ok(value: float | int, source: str, *, timestamp: str | None = None, scope: str = "unknown") -> MetricValue:
    return MetricValue(value=value, status="ok", source=source, timestamp=timestamp, scope=scope)


def unavailable(source: str, reason: str, *, timestamp: str | None = None, scope: str = "unknown") -> MetricValue:
    return MetricValue(value=None, status="unavailable", source=source, reason=reason, timestamp=timestamp, scope=scope)


def invalid(source: str, reason: str, *, value: float | int | None = None, timestamp: str | None = None, scope: str = "unknown") -> MetricValue:
    return MetricValue(value=value, status="invalid", source=source, reason=reason, timestamp=timestamp, scope=scope)


def estimated(value: float | int | None, source: str, reason: str, *, timestamp: str | None = None, scope: str = "unknown") -> MetricValue:
    return MetricValue(value=value, status="estimated", source=source, reason=reason, timestamp=timestamp, scope=scope)


def metric_from_raw(value: Any, *, source: str, reason: str = "missing", scope: str = "unknown") -> MetricValue:
    parsed = parse_number(value)
    if parsed is None:
        return unavailable(source, reason, scope=scope)
    return ok(parsed, source, scope=scope)


def parse_number(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def valid_values(rows: list[dict[str, Any]], column: str) -> list[float]:
    values: list[float] = []
    status_column = f"{column}_status"
    for row in rows:
        status = str(row.get(status_column, "ok") or "ok")
        if status not in {"ok", "estimated"}:
            continue
        parsed = parse_number(row.get(column))
        if parsed is None:
            continue
        values.append(parsed)
    return values


def percentile(values: list[float], q: float) -> float | None:
    """Inclusive linear interpolation percentile.

    This is equivalent to Excel/NumPy's common inclusive percentile method:
    rank = (n - 1) * q, linearly interpolated between neighboring sorted values.
    """

    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return float(ordered[low] * (1 - weight) + ordered[high] * weight)


def descriptive_stats(rows: list[dict[str, Any]], column: str) -> dict[str, Any]:
    values = valid_values(rows, column)
    total = len(rows)
    if not values:
        return {
            "metric": column,
            "valid_n": 0,
            "total_n": total,
            "mean": "",
            "median": "",
            "std": "",
            "min": "",
            "max": "",
            "p50": "",
            "p95": "",
        }
    return {
        "metric": column,
        "valid_n": len(values),
        "total_n": total,
        "mean": mean(values),
        "median": median(values),
        "std": pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
    }
