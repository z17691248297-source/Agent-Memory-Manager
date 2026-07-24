from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from agentmem.experiment import utc_timestamp
from agentmem.metrics.metric_models import MetricValue, metric_from_raw, ok, unavailable


PROMETHEUS_ALIASES = {
    "gpu_memory_used_mb": [
        "vllm:gpu_memory_used_bytes",
        "vllm_gpu_memory_used_bytes",
        "vllm:gpu_memory_used_mb",
        "vllm_gpu_memory_used_mb",
    ],
    "gpu_memory_reserved_mb": [
        "vllm:gpu_memory_reserved_bytes",
        "vllm_gpu_memory_reserved_bytes",
        "vllm:gpu_memory_reserved_mb",
        "vllm_gpu_memory_reserved_mb",
    ],
    "kv_cache_usage": ["vllm:gpu_cache_usage_perc", "vllm_gpu_cache_usage_perc", "vllm:kv_cache_usage"],
    "kv_cache_used_blocks": ["vllm:kv_cache_used_blocks", "vllm_kv_cache_used_blocks"],
    "kv_cache_total_blocks": ["vllm:kv_cache_total_blocks", "vllm_kv_cache_total_blocks"],
    "prefix_cache_hits": ["vllm:prefix_cache_hits_total", "vllm_prefix_cache_hits_total"],
    "prefix_cache_misses": ["vllm:prefix_cache_misses_total", "vllm_prefix_cache_misses_total"],
    "cached_prompt_tokens": [
        "vllm:cached_prompt_tokens_total",
        "vllm_cached_prompt_tokens_total",
        "vllm:prompt_tokens_cached_total",
    ],
    "evicted_blocks": ["vllm:kv_cache_evictions_total", "vllm_kv_cache_evictions_total"],
    "active_requests": ["vllm:num_requests_total", "vllm_num_requests_total", "vllm:active_requests"],
    "waiting_requests": ["vllm:num_requests_waiting", "vllm_num_requests_waiting"],
    "running_requests": ["vllm:num_requests_running", "vllm_num_requests_running"],
}

CACHE_STATS_FIELDS = [
    "gpu_memory_used_mb",
    "gpu_memory_reserved_mb",
    "kv_cache_usage",
    "kv_cache_used_blocks",
    "kv_cache_total_blocks",
    "prefix_cache_hits",
    "prefix_cache_misses",
    "prefix_cache_hit_rate",
    "cached_prompt_tokens",
    "evicted_blocks",
    "active_requests",
    "waiting_requests",
    "running_requests",
]


@dataclass
class ServerMetricSnapshot:
    timestamp: str
    source: str
    scope: str
    available: bool
    reason: str = ""
    service_version: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    concurrent_requests_present: bool = False
    isolated_dimensions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "scope": self.scope,
            "available": self.available,
            "reason": self.reason,
            "service_version": self.service_version,
            "raw": self.raw,
            "metrics": {key: value.as_plain_dict() for key, value in self.metrics.items()},
            "concurrent_requests_present": self.concurrent_requests_present,
            "isolated_dimensions": list(self.isolated_dimensions),
        }

    def to_row(self, prefix: str = "") -> dict[str, Any]:
        row: dict[str, Any] = {
            f"{prefix}server_metrics_available": self.available,
            f"{prefix}server_metrics_source": self.source,
            f"{prefix}server_metrics_scope": self.scope,
            f"{prefix}server_metrics_reason": self.reason,
            f"{prefix}server_version": self.service_version,
        }
        for name, metric in self.metrics.items():
            row.update(metric.to_dict(f"{prefix}{name}"))
        return row


class ModelServerMetricsCollector:
    """Collect model-server metrics without assuming local GPU access."""

    def __init__(
        self,
        *,
        metrics_url: str | None = None,
        cache_stats_url: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.metrics_url = str(metrics_url or "")
        self.cache_stats_url = str(cache_stats_url or "")
        self.timeout = float(timeout)

    def snapshot(self) -> ServerMetricSnapshot:
        if self.cache_stats_url:
            snapshot = self._cache_stats_snapshot()
            if snapshot.available:
                return snapshot
        if self.metrics_url:
            return self._prometheus_snapshot()
        return _unavailable_snapshot("model_server", "metrics_url_not_configured")

    def _cache_stats_snapshot(self) -> ServerMetricSnapshot:
        text, error = _http_get(self.cache_stats_url, self.timeout)
        if error:
            return _unavailable_snapshot(self.cache_stats_url, error)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return _unavailable_snapshot(self.cache_stats_url, f"invalid_json: {exc}")
        if not isinstance(payload, dict):
            return _unavailable_snapshot(self.cache_stats_url, "response_json_is_not_object")

        timestamp = utc_timestamp()
        scope = _scope_from_payload(payload)
        metrics: dict[str, MetricValue] = {}
        for field_name in CACHE_STATS_FIELDS:
            value = _find_metric_value(payload, field_name)
            metrics[field_name] = metric_from_raw(value, source=self.cache_stats_url, reason="field_missing", scope=scope)
        hits = metrics.get("prefix_cache_hits")
        misses = metrics.get("prefix_cache_misses")
        if metrics["prefix_cache_hit_rate"].value is None and hits and misses and hits.value is not None and misses.value is not None:
            denominator = float(hits.value) + float(misses.value)
            if denominator > 0:
                metrics["prefix_cache_hit_rate"] = ok(float(hits.value) / denominator, self.cache_stats_url, scope=scope)
        return ServerMetricSnapshot(
            timestamp=timestamp,
            source=self.cache_stats_url,
            scope=scope,
            available=True,
            service_version=str(payload.get("version") or payload.get("vllm_version") or ""),
            raw=payload,
            metrics=metrics,
            concurrent_requests_present=_concurrent_requests(metrics),
            isolated_dimensions=_isolated_dimensions(payload),
        )

    def _prometheus_snapshot(self) -> ServerMetricSnapshot:
        text, error = _http_get(self.metrics_url, self.timeout)
        if error:
            return _unavailable_snapshot(self.metrics_url, error)
        values = parse_prometheus_values(text)
        timestamp = utc_timestamp()
        metrics: dict[str, MetricValue] = {}
        for field_name, aliases in PROMETHEUS_ALIASES.items():
            value = _first_alias(values, aliases)
            if value is not None and aliases[0].endswith("_bytes"):
                value = value / (1024 * 1024)
            metrics[field_name] = metric_from_raw(value, source=self.metrics_url, reason="metric_missing", scope="global")
        hits = metrics.get("prefix_cache_hits")
        misses = metrics.get("prefix_cache_misses")
        if hits and misses and hits.value is not None and misses.value is not None:
            denominator = float(hits.value) + float(misses.value)
            if denominator > 0:
                metrics["prefix_cache_hit_rate"] = ok(float(hits.value) / denominator, self.metrics_url, scope="global")
            else:
                metrics["prefix_cache_hit_rate"] = unavailable(self.metrics_url, "no_prefix_cache_requests", scope="global")
        else:
            metrics["prefix_cache_hit_rate"] = unavailable(self.metrics_url, "prefix_hit_miss_metrics_missing", scope="global")
        return ServerMetricSnapshot(
            timestamp=timestamp,
            source=self.metrics_url,
            scope="global",
            available=True,
            raw={"prometheus_metric_count": len(values)},
            metrics=metrics,
            concurrent_requests_present=_concurrent_requests(metrics),
        )


def parse_prometheus_values(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_:][A-Za-z0-9_:]*)(?:\{[^}]*\})?\s+([-+0-9.eE]+)", line)
        if not match:
            continue
        name, raw_value = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            continue
        values[name] = max(values.get(name, value), value)
    return values


def _http_get(url: str, timeout: float) -> tuple[str, str | None]:
    last_error = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace"), None
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt < 2:
                time.sleep(0.05)
    return "", last_error


def _unavailable_snapshot(source: str, reason: str) -> ServerMetricSnapshot:
    timestamp = utc_timestamp()
    metrics = {field_name: unavailable(source, reason, timestamp=timestamp) for field_name in CACHE_STATS_FIELDS}
    return ServerMetricSnapshot(
        timestamp=timestamp,
        source=source,
        scope="unknown",
        available=False,
        reason=reason,
        metrics=metrics,
    )


def _first_alias(values: dict[str, float], aliases: list[str]) -> float | None:
    for name in aliases:
        if name in values:
            return values[name]
    return None


def _scope_from_payload(payload: dict[str, Any]) -> str:
    scope = str(payload.get("scope") or payload.get("metrics_scope") or "").lower()
    if scope:
        return scope
    if any(key in payload for key in ["by_agent", "by_session", "by_experiment"]):
        return "partitioned"
    return "global"


def _isolated_dimensions(payload: dict[str, Any]) -> list[str]:
    dimensions: list[str] = []
    for key in ["experiment_id", "run_id", "agent_id", "session_id", "branch_id", "cache_namespace", "segment_type"]:
        if key in payload or f"by_{key}" in payload:
            dimensions.append(key)
    for key in ["by_experiment", "by_run", "by_agent", "by_session", "by_branch", "by_namespace", "by_segment_type"]:
        if key in payload:
            dimensions.append(key.removeprefix("by_"))
    return sorted(set(dimensions))


def _find_metric_value(payload: Any, metric_name: str) -> Any:
    aliases = {
        metric_name,
        metric_name.replace("_mb", ""),
        f"cache_{metric_name}",
        f"num_{metric_name}",
    }
    if metric_name == "prefix_cache_hits":
        aliases.update({"prefix_hits", "cache_hits", "hit_count"})
    if metric_name == "prefix_cache_misses":
        aliases.update({"prefix_misses", "cache_misses", "miss_count"})
    if metric_name == "evicted_blocks":
        aliases.update({"eviction_count", "cache_evictions", "evicted"})
    if isinstance(payload, dict):
        for alias in aliases:
            if alias in payload:
                value = payload[alias]
                if isinstance(value, dict):
                    continue
                return value
        for key in ["metrics", "cache", "kv_cache", "stats", "totals"]:
            if key in payload:
                found = _find_metric_value(payload[key], metric_name)
                if found is not None:
                    return found
        for item in payload.values():
            found = _find_metric_value(item, metric_name)
            if found is not None:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_metric_value(item, metric_name)
            if found is not None:
                return found
    return None


def _concurrent_requests(metrics: dict[str, MetricValue]) -> bool:
    for key in ["active_requests", "waiting_requests", "running_requests"]:
        metric = metrics.get(key)
        if metric and metric.value is not None and float(metric.value) > 0:
            return True
    return False
