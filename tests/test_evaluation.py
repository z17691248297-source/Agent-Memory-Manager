from __future__ import annotations

import pytest

from agentmem.evaluation import evaluate_metric_checks, evaluate_task


def test_evaluate_task_requires_explicit_criteria() -> None:
    with pytest.raises(ValueError):
        evaluate_task({"task_id": "no_criteria"}, "answer", {})


def test_evaluate_task_checks_keywords_and_tools() -> None:
    task = {
        "task_id": "t1",
        "expected_tools": ["log_analyzer"],
        "answer_keywords": ["oom", "kv cache"],
        "success_threshold": 1.0,
    }
    result = evaluate_task(task, "OOM and KV cache are present.", {"tool_names": "log_analyzer"})
    assert result.success
    assert result.score == 1.0


def test_evaluate_metric_checks_reports_partial_score() -> None:
    result = evaluate_metric_checks({"a": True, "b": False})
    assert not result.success
    assert result.score == 0.5
