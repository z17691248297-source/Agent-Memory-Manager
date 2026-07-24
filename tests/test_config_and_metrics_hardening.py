from __future__ import annotations

import json

import pytest

from agentmem.config import ConfigError, load_config, validate_config
from agentmem.experiment import ExperimentIdGenerator
from agentmem.metrics.metric_models import descriptive_stats
from agentmem.metrics.server_metrics import ModelServerMetricsCollector
from agentmem.metrics.snapshot import cache_experiment_contaminated, compute_snapshot_delta
from agentmem.metrics.validation import validate_result_rows
from tests.utils.fake_openai_server import FakeAgentMemServer


def test_config_env_resolution_and_validation(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
llm:
  backend: ${BACKEND}
  model: ${MODEL}
  base_url: ${BASE_URL}
  timeout: 10
agent:
  max_steps: 2
extractor:
  enabled: false
vllm:
  enable_agent_meta: true
  agent_id: test_agent
  metrics_url: ${METRICS_URL}
  cache_stats_url: ${CACHE_URL}
benchmark:
  repeat: 1
  warmup: 0
cache_isolation:
  strategy: snapshot_delta
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("BACKEND", "vllm")
    monkeypatch.setenv("MODEL", "fake-model")
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:18080/v1")
    monkeypatch.setenv("METRICS_URL", "http://127.0.0.1:18080/metrics")
    monkeypatch.setenv("CACHE_URL", "http://127.0.0.1:18080/v1/agentmem/cache_stats")

    config = load_config(cfg, validate=True)

    assert config["llm"]["model"] == "fake-model"
    assert config["benchmark"]["repeat"] == 1


def test_config_rejects_invalid_values():
    with pytest.raises(ConfigError):
        validate_config({"llm": {"backend": "vllm", "model": "m", "base_url": "not-url", "timeout": 1}, "agent": {"max_steps": 1}, "benchmark": {"repeat": 1}})
    with pytest.raises(ConfigError):
        validate_config({"llm": {"backend": "mock", "model": "m", "base_url": "http://x/v1", "timeout": 1}, "agent": {"max_steps": 1}, "benchmark": {"repeat": 5}}, release=True)


def test_experiment_id_seed_is_stable_and_isolated():
    first = ExperimentIdGenerator(experiment_id="exp_fixed", seed=123).identity(scenario="tool-heavy", variant="baseline", model="m", trial_index=1)
    second = ExperimentIdGenerator(experiment_id="exp_fixed", seed=123).identity(scenario="tool-heavy", variant="baseline", model="m", trial_index=1)
    optimized = ExperimentIdGenerator(experiment_id="exp_fixed", seed=123).identity(scenario="tool-heavy", variant="optimized", model="m", trial_index=1)

    assert first == second
    assert first.session_id != optimized.session_id
    assert first.trial_id != optimized.trial_id


def test_metric_stats_exclude_unavailable_and_compute_p95():
    rows = [
        {"latency": "1", "latency_status": "ok"},
        {"latency": "", "latency_status": "unavailable"},
        {"latency": "3", "latency_status": "ok"},
    ]
    stats = descriptive_stats(rows, "latency")

    assert stats["valid_n"] == 2
    assert stats["total_n"] == 3
    assert stats["mean"] == 2
    assert stats["p95"] == pytest.approx(2.9)


def test_negative_count_invalidates_trial():
    result = validate_result_rows([{"trial_id": "t1", "extractor_success_count": "-1"}], file_name="x.csv")

    assert not result.valid
    assert result.invalid_trials[0].reason.startswith("extractor_success_count is negative")


def test_fake_metrics_server_snapshot_delta_and_contamination(monkeypatch):
    class FakeResponse:
        status = 200

        def __init__(self, text: str):
            self._text = text

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self._text.encode("utf-8")

    def fake_urlopen(url, timeout=0):
        text_url = str(url)
        if text_url.endswith("/v1/agentmem/cache_stats"):
            total = FakeAgentMemServer.prefix_hits + FakeAgentMemServer.prefix_misses
            return FakeResponse(
                json.dumps(
                    {
                        "version": "fake-test-server",
                        "scope": "global",
                        "kv_cache_usage": 0.25,
                        "kv_cache_used_blocks": 8 + FakeAgentMemServer.request_count,
                        "kv_cache_total_blocks": 128,
                        "prefix_cache_hits": FakeAgentMemServer.prefix_hits,
                        "prefix_cache_misses": FakeAgentMemServer.prefix_misses,
                        "prefix_cache_hit_rate": (FakeAgentMemServer.prefix_hits / total) if total else None,
                        "cached_prompt_tokens": FakeAgentMemServer.prefix_hits * 16,
                        "evicted_blocks": 0,
                        "active_requests": 0,
                        "waiting_requests": 0,
                        "running_requests": 0,
                    }
                )
            )
        return FakeResponse(
            "\n".join(
                [
                    "vllm:gpu_cache_usage_perc 0.25",
                    f"vllm:prefix_cache_hits_total {FakeAgentMemServer.prefix_hits}",
                    f"vllm:prefix_cache_misses_total {FakeAgentMemServer.prefix_misses}",
                    f"vllm:cached_prompt_tokens_total {FakeAgentMemServer.prefix_hits * 16}",
                    "vllm:num_requests_running 0",
                ]
            )
        )

    FakeAgentMemServer.request_count = 0
    FakeAgentMemServer.prefix_hits = 0
    FakeAgentMemServer.prefix_misses = 0
    monkeypatch.setattr("agentmem.metrics.server_metrics.urllib.request.urlopen", fake_urlopen)
    collector = ModelServerMetricsCollector(
        metrics_url="http://fake.test/metrics",
        cache_stats_url="http://fake.test/v1/agentmem/cache_stats",
        timeout=2,
    )
    before = collector.snapshot()
    # Mutate class counters to simulate service activity between snapshots.
    FakeAgentMemServer.prefix_hits += 2
    after = collector.snapshot()
    delta = compute_snapshot_delta(before, after)
    contaminated, reason = cache_experiment_contaminated(before, after, isolation_strategy="snapshot_delta")

    assert before.available is True
    assert delta.metrics["prefix_cache_hits"].value == 2
    assert contaminated is True
    assert reason in {"global_metrics_without_isolated_dimensions", "concurrent_requests_present"}
