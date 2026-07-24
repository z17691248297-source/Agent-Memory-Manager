from __future__ import annotations

import re
import urllib.error
import urllib.request
from typing import Any

from agentmem.metrics.metric_models import MetricValue, ok, unavailable
from agentmem.metrics.server_metrics import parse_prometheus_values

DEFAULT_VLLM_METRICS = {
    "prefix_cache_hit_rate": None,
    "prefix_cache_hit_rate_status": "unavailable",
    "prefix_cache_hit_rate_reason": "not_collected",
    "cached_prompt_tokens": None,
    "cached_prompt_tokens_status": "unavailable",
    "cached_prompt_tokens_reason": "not_collected",
    "kv_cache_usage": None,
    "kv_cache_usage_status": "unavailable",
    "kv_cache_usage_reason": "not_collected",
}


def fetch_vllm_metrics(metrics_url: str, timeout: float = 2.0) -> dict[str, Any]:
    """Best-effort vLLM Prometheus metrics reader.

    vLLM metric names change across releases, so this parser accepts several
    likely names and uses empty values plus status/reason fields when the
    endpoint is not reachable or a metric is absent.
    """
    metrics_url = str(metrics_url or "").strip()
    if not metrics_url:
        return _metric_rows(
            {
                "prefix_cache_hit_rate": unavailable("model_server", "metrics_url_not_configured", scope="unknown"),
                "cached_prompt_tokens": unavailable("model_server", "metrics_url_not_configured", scope="unknown"),
                "kv_cache_usage": unavailable("model_server", "metrics_url_not_configured", scope="unknown"),
            }
        )
    try:
        with urllib.request.urlopen(metrics_url, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return _metric_rows(
            {
                "prefix_cache_hit_rate": unavailable(metrics_url, str(exc), scope="global"),
                "cached_prompt_tokens": unavailable(metrics_url, str(exc), scope="global"),
                "kv_cache_usage": unavailable(metrics_url, str(exc), scope="global"),
            }
        )

    values = _parse_prometheus_values(text)
    return _metric_rows(
        {
            "prefix_cache_hit_rate": _first_metric(
                values,
                [
                    "vllm:prefix_cache_hit_rate",
                    "vllm_prefix_cache_hit_rate",
                    "vllm:gpu_prefix_cache_hit_rate",
                ],
                metrics_url,
            ),
            "cached_prompt_tokens": _first_metric(
                values,
                [
                    "vllm:cached_prompt_tokens_total",
                    "vllm_cached_prompt_tokens_total",
                    "vllm:prompt_tokens_cached_total",
                ],
                metrics_url,
            ),
            "kv_cache_usage": _first_metric(
                values,
                [
                    "vllm:gpu_cache_usage_perc",
                    "vllm_gpu_cache_usage_perc",
                    "vllm:kv_cache_usage",
                ],
                metrics_url,
            ),
        }
    )


def _parse_prometheus_values(text: str) -> dict[str, float]:
    return parse_prometheus_values(text)


def _first_metric(values: dict[str, float], names: list[str], source: str) -> MetricValue:
    for name in names:
        if name in values:
            return ok(values[name], source, scope="global")
    return unavailable(source, "metric_missing", scope="global")


def _metric_rows(metrics: dict[str, MetricValue]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for name, metric in metrics.items():
        row.update(metric.to_dict(name))
    return row
