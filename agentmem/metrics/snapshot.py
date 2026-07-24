from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentmem.metrics.metric_models import MetricValue, invalid, ok, unavailable
from agentmem.metrics.server_metrics import ServerMetricSnapshot


@dataclass(frozen=True)
class SnapshotDelta:
    before: ServerMetricSnapshot
    after: ServerMetricSnapshot
    metrics: dict[str, MetricValue]
    contaminated: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "metrics": {key: value.as_plain_dict() for key, value in self.metrics.items()},
            "contaminated": self.contaminated,
            "reason": self.reason,
        }


COUNTER_FIELDS = {
    "prefix_cache_hits",
    "prefix_cache_misses",
    "cached_prompt_tokens",
    "evicted_blocks",
}


def compute_snapshot_delta(before: ServerMetricSnapshot, after: ServerMetricSnapshot) -> SnapshotDelta:
    metrics: dict[str, MetricValue] = {}
    contaminated = before.concurrent_requests_present or after.concurrent_requests_present
    reason = "concurrent_requests_present" if contaminated else ""
    for name, after_metric in after.metrics.items():
        before_metric = before.metrics.get(name)
        if after_metric.value is None or before_metric is None or before_metric.value is None:
            metrics[name] = unavailable(after_metric.source, "before_or_after_metric_unavailable", scope=after_metric.scope)
            continue
        delta = float(after_metric.value) - float(before_metric.value)
        if name in COUNTER_FIELDS:
            if delta < 0:
                metrics[name] = invalid(after_metric.source, "counter_decreased_between_snapshots", value=delta, scope=after_metric.scope)
            else:
                metrics[name] = ok(delta, after_metric.source, scope=after_metric.scope)
        else:
            metrics[name] = ok(after_metric.value, after_metric.source, scope=after_metric.scope)
    return SnapshotDelta(before=before, after=after, metrics=metrics, contaminated=contaminated, reason=reason)


def cache_experiment_contaminated(before: ServerMetricSnapshot, after: ServerMetricSnapshot, *, isolation_strategy: str) -> tuple[bool, str]:
    if isolation_strategy in {"restart", "reset_endpoint", "namespace_isolation"}:
        return False, ""
    delta = compute_snapshot_delta(before, after)
    if delta.contaminated:
        return True, delta.reason
    if after.scope == "global" and not after.isolated_dimensions:
        return True, "global_metrics_without_isolated_dimensions"
    return False, ""
