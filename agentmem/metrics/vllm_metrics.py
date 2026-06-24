from __future__ import annotations

import re
import urllib.error
import urllib.request
from typing import Any


DEFAULT_VLLM_METRICS = {
    "prefix_cache_hit_rate": -1.0,
    "cached_prompt_tokens": -1.0,
    "kv_cache_usage": -1.0,
}


def fetch_vllm_metrics(metrics_url: str, timeout: float = 2.0) -> dict[str, float]:
    """Best-effort vLLM Prometheus metrics reader.

    vLLM metric names change across releases, so this parser accepts several
    likely names and falls back to -1 for every field when the endpoint is not
    reachable or a metric is absent.
    """
    try:
        with urllib.request.urlopen(metrics_url, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, TimeoutError):
        return dict(DEFAULT_VLLM_METRICS)

    metrics = dict(DEFAULT_VLLM_METRICS)
    values = _parse_prometheus_values(text)
    metrics["prefix_cache_hit_rate"] = _first_metric(
        values,
        [
            "vllm:prefix_cache_hit_rate",
            "vllm_prefix_cache_hit_rate",
            "vllm:gpu_prefix_cache_hit_rate",
        ],
    )
    metrics["cached_prompt_tokens"] = _first_metric(
        values,
        [
            "vllm:cached_prompt_tokens_total",
            "vllm_cached_prompt_tokens_total",
            "vllm:prompt_tokens_cached_total",
        ],
    )
    metrics["kv_cache_usage"] = _first_metric(
        values,
        [
            "vllm:gpu_cache_usage_perc",
            "vllm_gpu_cache_usage_perc",
            "vllm:kv_cache_usage",
        ],
    )
    return metrics


def _parse_prometheus_values(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
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


def _first_metric(values: dict[str, float], names: list[str]) -> float:
    for name in names:
        if name in values:
            return values[name]
    return -1.0
