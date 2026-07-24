#!/usr/bin/env python3
"""Enter-driven terminal demo for AgentMem.

The script is designed for screen recording: each step shows a short subtitle,
waits for Enter, then prints a compact command/result view from existing final
experiment outputs. It avoids long benchmark runs by default.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "results" / "final"


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentMem subtitle-style terminal demo.")
    parser.add_argument("--results-root", default=str(FINAL), help="Final results directory to display.")
    parser.add_argument("--auto", action="store_true", help="Do not wait for Enter; useful for smoke tests.")
    parser.add_argument("--live", action="store_true", help="Show live benchmark commands instead of only final results.")
    args = parser.parse_args()

    demo = Demo(Path(args.results_root), auto=args.auto, live=args.live)
    demo.run()
    return 0


class Demo:
    def __init__(self, results_root: Path, *, auto: bool = False, live: bool = False) -> None:
        self.results_root = results_root
        self.auto = auto
        self.live = live

    def run(self) -> None:
        self.clear()
        self.title(
            "AgentMem 演示",
            [
                "主题：面向智能体的内存管理系统设计与实现",
                "形式：字幕说明 + 按 Enter 执行下一步",
                "主线：AgentRuntime、事件溯源式记忆、工具结果外置、vLLM agent_meta/cache_stats",
            ],
        )
        self.pause()

        self.step_project_overview()
        self.step_runtime_flow()
        self.step_token_accounting()
        self.step_tool_store()
        self.step_memory_plan()
        self.step_agent_meta()
        self.step_cache_pressure()
        self.step_ttl_priority()
        self.step_report()
        self.ending()

    def step_project_overview(self) -> None:
        self.caption(
            "1. 项目目标",
            "AgentMem 解决长生命周期 Agent 的上下文膨胀问题：系统提示、工具 schema、工具结果、历史状态和分支记忆都需要被管理。",
        )
        self.command("find agentmem -maxdepth 2 -path '*/__pycache__' -prune -o -type f -print | sort | sed -n '1,60p'")
        self.run_shell("find agentmem -maxdepth 2 -path '*/__pycache__' -prune -o -type f -print | sort | sed -n '1,60p'")
        self.pause()

    def step_runtime_flow(self) -> None:
        self.caption(
            "2. 轻量 AgentRuntime",
            "运行时把一次请求拆成：用户输入 -> 工具路由 -> 工具执行 -> 构造记忆上下文 -> 调用 vLLM -> 记录指标。",
        )
        self.command("sed -n '42,152p' agentmem/runtime/agent.py")
        self.run_shell("sed -n '42,152p' agentmem/runtime/agent.py")
        self.pause()

    def step_token_accounting(self) -> None:
        self.caption(
            "3. token 统计方式",
            "本地先用轻量估算保证 benchmark 可运行；真实 vLLM 返回 usage 时，优先使用 prompt_tokens 和 completion_tokens。",
        )
        self.command("sed -n '24,36p' agentmem/memory/memory_object.py && sed -n '112,129p' agentmem/runtime/llm_client.py")
        self.run_shell("sed -n '24,36p' agentmem/memory/memory_object.py && sed -n '112,129p' agentmem/runtime/llm_client.py")
        self.print_csv(
            self.results_root / "main" / "summary.csv",
            columns=["scenario", "mode", "avg_prompt_tokens", "avg_latency", "success_rate", "avg_score"],
            limit=8,
        )
        self.pause()

    def step_tool_store(self) -> None:
        self.caption(
            "4. 工具调用与输出管理",
            "工具结果不直接全文塞进 prompt，而是保存 raw/chunks/index；prompt 只注入 result_id、summary 和 artifact refs。",
        )
        self.command("sed -n '21,84p' agentmem/tools/executor.py && sed -n '13,72p' agentmem/memory/tool_result_store.py")
        self.run_shell("sed -n '21,84p' agentmem/tools/executor.py && sed -n '13,72p' agentmem/memory/tool_result_store.py")
        self.print_csv(
            self.results_root / "main" / "summary.csv",
            columns=[
                "scenario",
                "mode",
                "avg_raw_tool_tokens",
                "avg_injected_tool_tokens",
                "avg_tool_compression_ratio",
            ],
            limit=10,
        )
        self.pause()

    def step_memory_plan(self) -> None:
        self.caption(
            "5. MemoryPlan 日志",
            "每次 LLM 请求前都会记录本轮包含了什么、排除了什么、估算 prompt tokens 和节省 tokens，方便解释优化来源。",
        )
        plan_file = self.first_file(self.results_root / "cache_pressure_on" / "memory_plan", "*.jsonl")
        if plan_file:
            self.command(f"head -n 2 {rel(plan_file)} | python -m json.tool")
            self.print_jsonl(plan_file, limit=2)
        else:
            self.warn("没有找到 memory_plan jsonl。")
        self.pause()

    def step_agent_meta(self) -> None:
        self.caption(
            "6. vLLM agent_meta 对接",
            "AgentMem 把 stage 映射成 segment_type，并通过 extra_body 传给 vLLM：shared_prefix/tool_schema 倾向保留，scratchpad/expired_branch 更易淘汰。",
        )
        self.command("sed -n '1,78p' agentmem/vllm/agent_meta.py")
        self.run_shell("sed -n '1,78p' agentmem/vllm/agent_meta.py")
        audit = self.results_root / "agent_meta_audit.csv"
        self.print_csv(
            audit,
            columns=["run_dir", "agent_meta_sent_true", "agent_meta_sent_false", "segment_types", "priorities_empty"],
            limit=8,
        )
        self.pause()

    def step_cache_pressure(self) -> None:
        self.caption(
            "7. cache-pressure 场景",
            "多 session、多轮请求、混合 segment_type，并制造较长 prompt，用来观察 agent_meta on/off 在 cache 统计上的差异。",
        )
        if self.live:
            self.command("python -m agentmem benchmark --scenario cache-pressure --agent-meta on --sessions 4 --output results_demo_cache_on")
            self.command("python -m agentmem benchmark --scenario cache-pressure --agent-meta off --sessions 4 --output results_demo_cache_off")
        self.print_csv(
            self.results_root / "cache_pressure_on" / "summary.csv",
            columns=[
                "scenario",
                "mode",
                "agent_meta_enabled",
                "agent_id",
                "avg_prompt_tokens",
                "cache_stats_available",
                "cache_total_blocks",
                "cache_agent_sessions",
            ],
            limit=8,
        )
        self.print_csv(
            self.results_root / "cache_pressure_compare_delta.csv",
            columns=["scenario", "metric", "off_before", "off_after", "off_delta", "on_before", "on_after", "on_delta", "delta_diff"],
            limit=12,
        )
        self.pause()

    def step_ttl_priority(self) -> None:
        self.caption(
            "8. TTL/Priority 场景",
            "不同上下文片段有不同优先级和 TTL：shared_prefix/tool_schema 高优先级，tool_result/scratchpad 低优先级，expired_branch 标记 drop。",
        )
        self.print_csv(
            self.results_root / "ttl_priority_on" / "ttl_priority.csv",
            columns=["stage", "segment_type", "priority", "ttl", "agent_meta_sent", "prompt_tokens", "latency"],
            limit=12,
        )
        before = self.first_file(self.results_root / "ttl_priority_on", "*before.json")
        after = self.first_file(self.results_root / "ttl_priority_on", "*after.json")
        if before and after:
            self.command(f"cache_stats before/after: {rel(before)} -> {rel(after)}")
            self.print_cache_pair(before, after)
        self.pause()

    def step_report(self) -> None:
        self.caption(
            "9. 报告汇总",
            "最终结果集中在 results/final，summary/report/compare/audit 文件可用于答辩和复现实验。",
        )
        self.command("find results/final -maxdepth 2 -type f | sort | sed -n '1,80p'")
        self.run_shell("find results/final -maxdepth 2 -type f | sort | sed -n '1,80p'")
        self.print_csv(
            self.results_root / "final_summary.csv",
            columns=["results_dir", "scenario", "mode", "agent_meta_enabled", "avg_prompt_tokens", "cache_stats_available", "agent_id"],
            limit=14,
        )
        self.pause()

    def ending(self) -> None:
        self.caption(
            "演示总结",
            "AgentMem 的核心价值是把 Agent 内部记忆结构显式化：客户端减少 prompt 膨胀，服务端通过 agent_meta 获得 KV cache 管理语义。",
        )
        self.bullets(
            [
                "轻量 AgentRuntime：统一编排工具、记忆和 LLM 调用。",
                "事件溯源式记忆：保留可回放事件，并生成压缩后的状态视图。",
                "工具结果外置：raw/chunks/index 保证可追溯，prompt 只注入摘要引用。",
                "vLLM agent_meta：让服务端区分 shared_prefix、tool_schema、tool_result、scratchpad、expired_branch。",
            ]
        )

    def title(self, title: str, lines: Iterable[str]) -> None:
        print(box(title, list(lines)))

    def caption(self, title: str, text: str) -> None:
        self.clear()
        print(box(title, wrap_text(text, width=76)))

    def command(self, text: str) -> None:
        print(f"\n$ {text}\n")

    def bullets(self, rows: Iterable[str]) -> None:
        for row in rows:
            print(f"  - {row}")

    def warn(self, message: str) -> None:
        print(f"\n[提示] {message}")

    def pause(self) -> None:
        if self.auto:
            print("\n[auto] 下一步\n")
            return
        input("\n按 Enter 进入下一步...")

    def clear(self) -> None:
        if self.auto:
            print("\n" + "=" * 88)
            return
        print("\033[2J\033[H", end="")

    def run_shell(self, command: str) -> None:
        result = subprocess.run(
            command,
            cwd=ROOT,
            shell=True,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        print(trim_output(result.stdout, max_lines=90))

    def print_csv(self, path: Path, *, columns: list[str], limit: int = 10) -> None:
        print(f"\n[CSV] {rel(path)}")
        if not path.exists():
            self.warn(f"文件不存在: {rel(path)}")
            return
        with path.open("r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        rows = rows[:limit]
        if not rows:
            self.warn("CSV 为空。")
            return
        existing = [col for col in columns if col in rows[0]]
        if not existing:
            existing = list(rows[0].keys())[: min(8, len(rows[0]))]
        print_table([{col: row.get(col, "") for col in existing} for row in rows], existing)

    def print_jsonl(self, path: Path, *, limit: int = 2) -> None:
        print(f"\n[JSONL] {rel(path)}")
        with path.open("r", encoding="utf-8") as file:
            for index, line in enumerate(file):
                if index >= limit:
                    break
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    print(line.strip())
                    continue
                compact = {
                    "run_id": payload.get("run_id"),
                    "agent_id": payload.get("agent_id"),
                    "stage": payload.get("stage"),
                    "context_id": payload.get("context_id"),
                    "segment_type": payload.get("segment_type"),
                    "priority": payload.get("priority"),
                    "ttl": payload.get("ttl"),
                    "included_items": payload.get("included_items"),
                    "external_refs": payload.get("external_refs"),
                    "excluded_items": payload.get("excluded_items"),
                    "estimated_prompt_tokens": payload.get("estimated_prompt_tokens"),
                    "estimated_saved_tokens": payload.get("estimated_saved_tokens"),
                    "agent_meta": payload.get("agent_meta"),
                }
                print(json.dumps(compact, ensure_ascii=False, indent=2))

    def print_cache_pair(self, before: Path, after: Path) -> None:
        before_data = load_json(before)
        after_data = load_json(after)
        keys = [
            "available",
            "cache_total_blocks",
            "cache_agent_sessions",
            "cache_tool_result_blocks",
            "cache_shared_prefix_blocks",
            "cache_scratchpad_blocks",
            "cache_expired_branch_blocks",
            "unavailable_reason",
        ]
        rows = []
        for key in keys:
            b = before_data.get(key, "")
            a = after_data.get(key, "")
            delta = ""
            if isinstance(b, (int, float)) and isinstance(a, (int, float)):
                delta = a - b
            rows.append({"metric": key, "before": b, "after": a, "delta": delta})
        print_table(rows, ["metric", "before", "after", "delta"])

    def first_file(self, directory: Path, pattern: str) -> Path | None:
        if not directory.exists():
            return None
        files = sorted(directory.glob(pattern))
        return files[0] if files else None


def print_table(rows: list[dict[str, object]], columns: list[str]) -> None:
    width = shutil.get_terminal_size((120, 24)).columns
    normalized = [
        {col: shorten(str(row.get(col, "")), max_len=max(12, min(36, width // max(2, len(columns)) - 2))) for col in columns}
        for row in rows
    ]
    widths = {
        col: max(len(col), *(len(str(row.get(col, ""))) for row in normalized))
        for col in columns
    }
    print("  " + " | ".join(col.ljust(widths[col]) for col in columns))
    print("  " + "-+-".join("-" * widths[col] for col in columns))
    for row in normalized:
        print("  " + " | ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


def box(title: str, lines: list[str]) -> str:
    width = 84
    top = "┌" + "─" * (width - 2) + "┐"
    mid = "├" + "─" * (width - 2) + "┤"
    bottom = "└" + "─" * (width - 2) + "┘"
    body = [top, f"│ {title:<{width - 4}} │", mid]
    for line in lines:
        for wrapped in wrap_text(line, width=width - 6):
            body.append(f"│ {wrapped:<{width - 4}} │")
    body.append(bottom)
    return "\n".join(body)


def wrap_text(text: str, width: int = 76) -> list[str]:
    if len(text) <= width:
        return [text]
    return textwrap.wrap(text, width=width, break_long_words=False, replace_whitespace=False)


def trim_output(text: str, *, max_lines: int) -> str:
    lines = text.rstrip().splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    head = lines[: max_lines - 4]
    return "\n".join(head + ["...", f"[已省略 {len(lines) - len(head)} 行输出]"])


def shorten(text: str, *, max_len: int) -> str:
    text = text.replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
