from __future__ import annotations

from agentmem.event_memory.extractor import ExternalMemoryDeltaExtractor, extractor_config_from_runtime


def test_extractor_enabled_config_is_read() -> None:
    config = {
        "extractor": {
            "enabled": True,
            "backend": "vllm",
            "base_url": "http://127.0.0.1:9000/v1",
            "api_key": "EMPTY",
            "model": "Qwen3.5-9B",
            "temperature": 0,
            "max_tokens": 1024,
            "timeout": 120,
        }
    }

    extractor = extractor_config_from_runtime(config)

    assert extractor.enabled is True
    assert extractor.backend == "vllm"
    assert extractor.base_url == "http://127.0.0.1:9000/v1"
    assert extractor.model == "Qwen3.5-9B"


def test_extractor_failure_falls_back_to_empty_delta() -> None:
    config = extractor_config_from_runtime(
        {
            "extractor": {
                "enabled": True,
                "base_url": "http://127.0.0.1:9/v1",
                "model": "missing",
                "timeout": 0.01,
            }
        }
    )
    extractor = ExternalMemoryDeltaExtractor(config)

    delta = extractor.extract_memory_delta({"current_query": "hello", "assistant_response": "ok"})

    assert delta.is_empty()
    assert extractor.last_error
