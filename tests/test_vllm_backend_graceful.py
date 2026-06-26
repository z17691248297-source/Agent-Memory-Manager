from __future__ import annotations

from agentmem.cli import main


def test_vllm_backend_unavailable_has_clear_error(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.delenv("AGENTMEM_LLM_BACKEND", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "llm:",
                "  backend: vllm",
                "  model: missing-test-model",
                "  base_url: http://127.0.0.1:9/v1",
                "  api_key: EMPTY",
                "  temperature: 0.2",
                "  max_tokens: 8",
                "  timeout: 0.2",
                "benchmark:",
                "  output_dir: results",
                "  repeat: 1",
                "memory:",
                "  recent_rounds: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    code = main(
        [
            "benchmark",
            "--scenario",
            "prefix-cache",
            "--backend",
            "vllm",
            "--output",
            str(tmp_path / "results"),
            "--config",
            str(config),
        ]
    )

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code == 1
    assert "vLLM backend is unavailable. Please check llm.base_url in configs/config.yaml." in combined
    assert "Traceback" not in combined
