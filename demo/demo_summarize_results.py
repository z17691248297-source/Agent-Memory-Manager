from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd


RED = "\033[31m"
RESET = "\033[0m"


def main() -> int:
    args = _parse_args()
    path = _resolve_input(args.input)
    if path is None:
        print("ERROR: 未找到 final_summary.csv")
        return 1

    df = pd.read_csv(path)
    print(_red("AgentMem final benchmark 精选摘要"))
    print(f"{_red('输入文件')}: {path}")
    print("说明: 只展示 4 条录屏结论；cache-pressure 只验证 agent_meta/cache_stats 链路。")

    _summarize_tool_heavy(df)
    _summarize_multi_stage(df)
    _summarize_branching(df)
    _summarize_cache_pressure(df)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print a compact video-friendly summary from final_summary.csv.")
    parser.add_argument("--input", type=Path, default=Path("results/final/final_summary.csv"))
    return parser.parse_args()


def _resolve_input(path: Path) -> Path | None:
    if path.exists():
        return path
    fallback = Path("final_summary.csv")
    if fallback.exists():
        return fallback
    return None


def _summarize_tool_heavy(df: pd.DataFrame) -> None:
    rows = _pick_tool_heavy_rows(df)
    if rows is None:
        print(f"- {_red('工具结果外置')}: 未找到该场景结果")
        return
    baseline, optimized = rows
    base_prompt = _number(baseline, "avg_prompt_tokens")
    opt_prompt = _number(optimized, "avg_prompt_tokens")
    base_injected = _number(baseline, "avg_injected_tool_tokens")
    opt_injected = _number(optimized, "avg_injected_tool_tokens")
    print(
        f"- {_red('工具结果外置')}: prompt {_fmt_number(base_prompt)} -> {_fmt_number(opt_prompt)} "
        f"({_pct_reduction(base_prompt, opt_prompt)}); injected tool tokens "
        f"{_fmt_number(base_injected)} -> {_fmt_number(opt_injected)} "
        f"({_pct_reduction(base_injected, opt_injected)}); "
        f"success {_success_pair(baseline, optimized)}"
    )


def _pick_tool_heavy_rows(df: pd.DataFrame) -> tuple[pd.Series, pd.Series] | None:
    base = df[(df.get("scenario") == "tool-heavy") & (df.get("mode").isin(["baseline", "optimized"]))]
    if base.empty:
        return None
    if "agent_meta_enabled" in base.columns:
        with_meta = base[base["agent_meta_enabled"].map(_boolish) == True]  # noqa: E712
        pair = _baseline_optimized_pair(with_meta)
        if pair is not None:
            return pair
        without_meta_flag = base[base["agent_meta_enabled"].isna()]
        pair = _baseline_optimized_pair(without_meta_flag)
        if pair is not None:
            return pair
    return _baseline_optimized_pair(base)


def _summarize_multi_stage(df: pd.DataFrame) -> None:
    rows = df[df.get("scenario") == "multi-stage"]
    full = _single_mode(rows, "full_history")
    event = _single_mode(rows, "event_sourced_memory")
    if full is None or event is None:
        print(f"- {_red('事件溯源记忆')}: 未找到该场景结果")
        return
    full_prompt = _number(full, "avg_prompt_tokens")
    event_prompt = _number(event, "avg_prompt_tokens")
    print(
        f"- {_red('事件溯源记忆')}: prompt {_fmt_number(full_prompt)} -> {_fmt_number(event_prompt)} "
        f"({_pct_reduction(full_prompt, event_prompt)}); "
        f"success {_fmt_pct(_number(full, 'success_rate'))} -> {_fmt_pct(_number(event, 'success_rate'))}"
    )


def _summarize_branching(df: pd.DataFrame) -> None:
    rows = df[df.get("scenario") == "branching"]
    pair = _baseline_optimized_pair(rows)
    if pair is None:
        print(f"- {_red('分支共享')}: 未找到该场景结果")
        return
    baseline, optimized = pair
    base_prompt = _number(baseline, "avg_prompt_tokens")
    opt_prompt = _number(optimized, "avg_prompt_tokens")
    print(
        f"- {_red('分支共享')}: prompt {_fmt_number(base_prompt)} -> {_fmt_number(opt_prompt)} "
        f"({_pct_reduction(base_prompt, opt_prompt)}); "
        f"branch saving {_fmt_pct(_number(optimized, 'avg_branch_saving_ratio'), already_percent=False)}"
    )


def _summarize_cache_pressure(df: pd.DataFrame) -> None:
    rows = df[df.get("scenario") == "cache-pressure"]
    if rows.empty or "agent_meta_enabled" not in rows.columns:
        print(f"- {_red('agent_meta/cache_stats')}: 未找到该场景结果")
        return
    on = _meta_row(rows, True)
    off = _meta_row(rows, False)
    if on is None or off is None:
        print(f"- {_red('agent_meta/cache_stats')}: 未找到该场景结果")
        return
    print(
        f"- {_red('agent_meta/cache_stats')}: on/off 都可运行; "
        f"success on={_fmt_pct(_number(on, 'success_rate'))}, off={_fmt_pct(_number(off, 'success_rate'))}; "
        f"cache_stats on={_clean(on.get('cache_stats_available'))}, off={_clean(off.get('cache_stats_available'))}; "
        "不宣称该场景性能一定提升。"
    )


def _baseline_optimized_pair(rows: pd.DataFrame) -> tuple[pd.Series, pd.Series] | None:
    baseline = _single_mode(rows, "baseline")
    optimized = _single_mode(rows, "optimized")
    if baseline is None or optimized is None:
        return None
    return baseline, optimized


def _single_mode(rows: pd.DataFrame, mode: str) -> pd.Series | None:
    selected = rows[rows.get("mode") == mode]
    if selected.empty:
        return None
    return selected.iloc[0]


def _meta_row(rows: pd.DataFrame, enabled: bool) -> pd.Series | None:
    selected = rows[rows["agent_meta_enabled"].map(_boolish) == enabled]
    if selected.empty:
        return None
    return selected.iloc[0]


def _number(row: pd.Series, column: str) -> float | None:
    value = row.get(column)
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_reduction(baseline: float | None, optimized: float | None) -> str:
    if baseline in (None, 0) or optimized is None:
        return "无可用数据"
    return _fmt_pct((baseline - optimized) / baseline, already_percent=False)


def _success_pair(baseline: pd.Series, optimized: pd.Series) -> str:
    return f"baseline={_fmt_pct(_number(baseline, 'success_rate'))}, optimized={_fmt_pct(_number(optimized, 'success_rate'))}"


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "无可用数据"
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.2f}"


def _fmt_pct(value: float | None, *, already_percent: bool = True) -> str:
    if value is None:
        return "无可用数据"
    number = value if already_percent else value * 100
    return f"{number:.2f}%"


def _clean(value: Any) -> str:
    if value is None:
        return "无可用数据"
    if isinstance(value, float) and pd.isna(value):
        return "无可用数据"
    text = str(value)
    return "无可用数据" if text.lower() == "nan" else text


def _boolish(value: Any) -> bool | None:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def _red(text: str) -> str:
    return f"{RED}{text}{RESET}"


if __name__ == "__main__":
    raise SystemExit(main())
