from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EvaluationResult:
    success: bool
    score: float
    failure_reason: str
    passed_checks: int
    total_checks: int


def evaluate_task(
    task: Mapping[str, Any],
    answer: str,
    metrics: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
) -> EvaluationResult:
    """Evaluate a benchmark task from explicit JSONL criteria.

    The evaluator is intentionally deterministic: every successful task must
    satisfy criteria declared in the workload, rather than inheriting a default
    success flag from the runtime.
    """
    context = context or {}
    checks: list[tuple[str, bool]] = []

    if bool(task.get("expect_answer", False)):
        checks.append(("answer_present", bool(answer.strip())))

    actual_tools = _tool_set(metrics.get("tool_names", context.get("tool_names", "")))
    for tool_name in task.get("expected_tools") or []:
        checks.append((f"expected_tool:{tool_name}", str(tool_name) in actual_tools))

    answer_haystack = _normalize("\n".join([answer, str(context.get("answer_extra", ""))]))
    for keyword in task.get("answer_keywords") or []:
        checks.append((f"answer_keyword:{keyword}", _normalize(str(keyword)) in answer_haystack))

    branch_haystack = _normalize(str(context.get("branch_text", answer)))
    for keyword in task.get("branch_keywords") or []:
        checks.append((f"branch_keyword:{keyword}", _normalize(str(keyword)) in branch_haystack))

    if "min_branch_count" in task:
        branch_count = _to_float(metrics.get("branch_count", context.get("branch_count")), None)
        checks.append(("min_branch_count", branch_count is not None and branch_count >= float(task["min_branch_count"])))

    expected_stages = task.get("expected_stages") or []
    if expected_stages:
        completed = list(context.get("completed_stages") or [])
        checks.append(("expected_stages", completed == list(expected_stages)))

    for metric_name, min_value in (task.get("min_metrics") or {}).items():
        value = _to_float(metrics.get(metric_name), None)
        checks.append((f"min_metric:{metric_name}", value is not None and value >= float(min_value)))

    for metric_name, max_value in (task.get("max_metrics") or {}).items():
        value = _to_float(metrics.get(metric_name), None)
        checks.append((f"max_metric:{metric_name}", value is not None and value <= float(max_value)))

    if not checks:
        task_id = task.get("task_id", "<unknown>")
        raise ValueError(f"task has no evaluator criteria: {task_id}")

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    score = passed / total
    threshold = float(task.get("success_threshold", 1.0))
    failed = [name for name, ok in checks if not ok]
    return EvaluationResult(
        success=score >= threshold,
        score=round(score, 6),
        failure_reason=";".join(failed),
        passed_checks=passed,
        total_checks=total,
    )


def evaluate_metric_checks(checks: Mapping[str, bool]) -> EvaluationResult:
    """Evaluate non-task benchmark rows from named boolean checks."""
    if not checks:
        raise ValueError("metric evaluation requires at least one check")
    passed = sum(1 for ok in checks.values() if ok)
    total = len(checks)
    failed = [name for name, ok in checks.items() if not ok]
    score = passed / total
    return EvaluationResult(
        success=passed == total,
        score=round(score, 6),
        failure_reason=";".join(failed),
        passed_checks=passed,
        total_checks=total,
    )


def evaluation_fields(result: EvaluationResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "score": result.score,
        "failure_reason": result.failure_reason,
        "passed_checks": result.passed_checks,
        "total_checks": result.total_checks,
    }


def _tool_set(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if str(item)}
    return {part for part in str(value).split(",") if part}


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _to_float(value: Any, default: float | None = 0.0) -> float | None:
    if value in {None, ""}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
