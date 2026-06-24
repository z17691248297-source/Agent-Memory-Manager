from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from agentmem.benchmark import BenchmarkOptions, run_benchmark
from agentmem.metrics.collector import MetricsCollector
from agentmem.metrics.summarizer import summarize_results
from agentmem.runtime.factory import PROJECT_ROOT, build_agent
from agentmem.runtime.llm_factory import load_runtime_config
from agentmem.tools.tool_registry import build_default_registry


DEFAULT_WORKLOADS = (
    PROJECT_ROOT / "benchmarks" / "workloads" / "multi_turn.jsonl",
    PROJECT_ROOT / "benchmarks" / "workloads" / "tool_call.jsonl",
)
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "config.yaml"
DEFAULT_RESULTS = PROJECT_ROOT / "results"
COMMANDS = {"run", "ask", "chat", "eval", "benchmark", "report", "config", "tools", "results", "clean", "help"}
STAGES = {"planning", "tool_calling", "reflection", "branching", "final_answer"}


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args_for_parser = normalize_argv(raw_args)
    parser = build_parser()
    args = parser.parse_args(args_for_parser)

    if args.command in {"run", "ask"}:
        return run_once(args)
    if args.command == "chat":
        return chat(args)
    if args.command == "eval":
        return eval_workloads(args)
    if args.command == "benchmark":
        return benchmark_command(args)
    if args.command == "report":
        return report_command(args)
    if args.command == "config":
        return config_command(args)
    if args.command == "tools":
        return tools_command(args)
    if args.command == "results":
        return results_command(args)
    if args.command == "clean":
        return clean_command(args)
    parser.print_help()
    return 2


def normalize_argv(argv: list[str]) -> list[str]:
    """Support Codex-like shorthand:

    - `agentmem` starts chat.
    - `agentmem "prompt"` runs one prompt.
    - `agentmem --stage tool_calling "prompt"` also runs one prompt.
    """
    if not argv:
        return ["chat"]
    first = argv[0]
    if first in {"-h", "--help", "help"}:
        return ["--help"]
    if first not in COMMANDS:
        return ["run", *argv]
    return argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentmem", description="AgentMem CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", aliases=["ask"], help="run one prompt")
    add_runtime_args(run)
    run.add_argument("prompt", nargs="*", help="user input; stdin is used when omitted")
    run.add_argument("--stage", default="planning", choices=sorted(STAGES))
    run.add_argument("--json", action="store_true", help="print answer and metrics as JSON")

    chat_cmd = sub.add_parser("chat", help="interactive session")
    add_runtime_args(chat_cmd)
    chat_cmd.add_argument("--stage", default="planning", choices=sorted(STAGES))

    eval_cmd = sub.add_parser("eval", help="run fixed JSONL workloads and write metrics CSV")
    add_runtime_args(eval_cmd)
    eval_cmd.add_argument(
        "--workload",
        action="append",
        type=Path,
        help="JSONL workload path; can be passed multiple times",
    )
    eval_cmd.add_argument("--output", type=Path, default=DEFAULT_RESULTS / "cli_eval.csv")
    eval_cmd.add_argument("--json", action="store_true", help="print summary as JSON")

    benchmark = sub.add_parser("benchmark", help="run AgentMem benchmark scenarios")
    benchmark.add_argument(
        "--scenario",
        choices=["tool-heavy", "long-session", "multi-stage", "branching", "prefix-cache", "ablation", "all"],
        default="all",
    )
    benchmark.add_argument("--all", action="store_true", help="run every benchmark scenario")
    benchmark.add_argument("--mode", choices=["baseline", "optimized", "both"], default="both")
    benchmark.add_argument(
        "--backend",
        choices=["mock", "vllm", "openai_compatible", "openai-compatible", "openai"],
        default=None,
    )
    benchmark.add_argument("--repeat", type=int, default=None)
    benchmark.add_argument("--output", type=Path, default=None)
    benchmark.add_argument("--config", type=Path, default=DEFAULT_CONFIG)

    report = sub.add_parser("report", help="generate results/report.md from benchmark CSVs")
    report.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    report.add_argument("--config", type=Path, default=DEFAULT_CONFIG)

    config = sub.add_parser("config", help="show or edit model/runtime config")
    config.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    config_sub = config.add_subparsers(dest="config_command")
    config_sub.add_parser("show", help="print config")
    get_cmd = config_sub.add_parser("get", help="read a dotted config key")
    get_cmd.add_argument("key")
    set_cmd = config_sub.add_parser("set", help="set a dotted config key")
    set_cmd.add_argument("key")
    set_cmd.add_argument("value")
    use_cmd = config_sub.add_parser("use", help="switch model backend")
    use_cmd.add_argument("backend", choices=["mock", "vllm", "openai", "openai_compatible", "openai-compatible"])
    use_cmd.add_argument("--base-url")
    use_cmd.add_argument("--model")
    use_cmd.add_argument("--api-key-env")
    use_cmd.add_argument("--api-key")

    tools = sub.add_parser("tools", help="list available tools")
    tools.add_argument("tool_command", nargs="?", choices=["list", "show"], default="list")
    tools.add_argument("name", nargs="?")
    tools.add_argument("--json", action="store_true")

    results = sub.add_parser("results", help="inspect generated result artifacts")
    results.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    results.add_argument("--json", action="store_true")

    clean = sub.add_parser("clean", help="delete generated results artifacts")
    clean.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    return parser


def add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=["optimized", "baseline"], default="optimized")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)


def run_once(args: argparse.Namespace) -> int:
    prompt = prompt_from_args(args.prompt)
    if not prompt:
        raise SystemExit("empty prompt")
    agent = build_agent(config_path=args.config, results_dir=args.results_dir, memory_mode=args.mode)
    answer, metrics = agent.run(prompt, stage=args.stage)
    if args.json:
        print(json.dumps({"answer": answer, "metrics": metrics}, ensure_ascii=False, indent=2))
    else:
        print(answer)
        print_metrics(metrics)
    return 0


def prompt_from_args(prompt_args: list[str] | str | None) -> str:
    if isinstance(prompt_args, list) and prompt_args:
        return " ".join(prompt_args).strip()
    if isinstance(prompt_args, str) and prompt_args:
        return prompt_args.strip()
    return sys.stdin.read().strip()


def chat(args: argparse.Namespace) -> int:
    state = {
        "stage": args.stage,
        "mode": args.mode,
        "last_metrics": None,
    }
    agent = build_agent(config_path=args.config, results_dir=args.results_dir, memory_mode=state["mode"])
    print("AgentMem CLI. Type /help for commands, /exit to quit.")
    while True:
        try:
            prompt = input(f"[{state['mode']}:{state['stage']}] > ").strip()
        except EOFError:
            print()
            break
        if not prompt:
            continue
        if prompt.startswith("/"):
            should_exit, agent = handle_chat_command(prompt, args, state, agent)
            if should_exit:
                break
            continue
        answer, metrics = agent.run(prompt, stage=str(state["stage"]))
        state["last_metrics"] = metrics
        print(answer)
        print_metrics(metrics)
    return 0


def handle_chat_command(prompt: str, args: argparse.Namespace, state: dict[str, Any], agent: Any) -> tuple[bool, Any]:
    parts = prompt.split()
    command = parts[0].lower()
    if command in {"/exit", "/quit", "/q"}:
        return True, agent
    if command == "/help":
        print_chat_help()
        return False, agent
    if command == "/stage":
        if len(parts) != 2 or parts[1] not in STAGES:
            print(f"usage: /stage {'|'.join(sorted(STAGES))}")
        else:
            state["stage"] = parts[1]
            print(f"stage: {state['stage']}")
        return False, agent
    if command == "/mode":
        if len(parts) != 2 or parts[1] not in {"optimized", "baseline"}:
            print("usage: /mode optimized|baseline")
        else:
            state["mode"] = parts[1]
            agent = build_agent(config_path=args.config, results_dir=args.results_dir, memory_mode=state["mode"])
            print(f"mode: {state['mode']} (session reset)")
        return False, agent
    if command == "/reset":
        agent = build_agent(config_path=args.config, results_dir=args.results_dir, memory_mode=state["mode"])
        state["last_metrics"] = None
        print("session reset")
        return False, agent
    if command == "/metrics":
        if state["last_metrics"]:
            print_metrics(state["last_metrics"])
        else:
            print("no metrics yet")
        return False, agent
    if command == "/tools":
        print_tools(json_output=False)
        return False, agent
    if command == "/config":
        print_config_summary(args.config)
        return False, agent
    if command == "/results":
        print_results_summary(args.results_dir)
        return False, agent
    print("unknown command; type /help")
    return False, agent


def print_chat_help() -> None:
    print(
        "\n".join(
            [
                "Commands:",
                "  /help                 show this help",
                "  /stage <stage>        set planning/tool_calling/reflection/branching/final_answer",
                "  /mode <mode>          set optimized/baseline and reset session",
                "  /reset                reset current session",
                "  /metrics              show last turn metrics",
                "  /tools                list tools",
                "  /config               show active model config",
                "  /results              show result artifact summary",
                "  /exit                 quit",
            ]
        )
    )


def eval_workloads(args: argparse.Namespace) -> int:
    workload_paths = args.workload or list(DEFAULT_WORKLOADS)
    agent = build_agent(config_path=args.config, results_dir=args.results_dir, memory_mode=args.mode)
    collector = MetricsCollector(args.output)
    total = 0
    expectation_failures = 0

    for item in load_workloads(workload_paths):
        _, metrics = agent.run(str(item["input"]), stage=str(item.get("stage", "planning")))
        metrics["experiment"] = f"cli_{args.mode}"
        collector.record(metrics)
        total += 1
        expected_tools = set(item.get("expected_tools") or [])
        if expected_tools:
            actual_tools = set(str(metrics.get("tool_names", "")).split(",")) - {""}
            if not expected_tools.issubset(actual_tools):
                expectation_failures += 1

    path = collector.write_csv()
    summary = {"tasks": total, "output": str(path), "expectation_failures": expectation_failures}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"ran {total} tasks; metrics written to {path}")
        if expectation_failures:
            print(f"tool expectation failures: {expectation_failures}")
    return 1 if expectation_failures else 0


def config_command(args: argparse.Namespace) -> int:
    command = args.config_command or "show"
    config = load_runtime_config(args.config)
    if command == "show":
        print(dump_config(config))
        return 0
    if command == "get":
        value = get_nested(config, args.key)
        print(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value)
        return 0
    if command == "set":
        set_nested(config, args.key, parse_scalar(args.value))
        save_config(args.config, config)
        print(f"set {args.key} = {get_nested(config, args.key)}")
        return 0
    if command == "use":
        backend = args.backend.replace("-", "_")
        llm = dict(config.get("llm") or {})
        llm["backend"] = backend
        if args.base_url:
            llm["base_url"] = args.base_url
        elif backend == "vllm":
            llm.setdefault("base_url", "http://localhost:8000/v1")
            llm.setdefault("api_key", "EMPTY")
        if args.model:
            llm["model"] = args.model
        if args.api_key_env:
            llm["api_key_env"] = args.api_key_env
        if args.api_key:
            llm["api_key"] = args.api_key
        config["llm"] = llm
        save_config(args.config, config)
        print_config_summary(args.config)
        return 0
    raise SystemExit(f"unknown config command: {command}")


def tools_command(args: argparse.Namespace) -> int:
    if args.tool_command == "show":
        if not args.name:
            raise SystemExit("usage: agentmem tools show <name>")
        return print_tool_detail(args.name, args.json)
    print_tools(json_output=args.json)
    return 0


def results_command(args: argparse.Namespace) -> int:
    summary = results_summary(args.results_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else format_results_summary(summary))
    return 0


def clean_command(args: argparse.Namespace) -> int:
    clean_results(args.results_dir)
    print(f"results cleaned: {args.results_dir}")
    return 0


def benchmark_command(args: argparse.Namespace) -> int:
    try:
        config = load_runtime_config(args.config)
        benchmark_config = dict(config.get("benchmark") or {})
        options = BenchmarkOptions(
            scenario="all" if args.all else args.scenario,
            mode=args.mode,
            backend=_normalize_backend(args.backend or dict(config.get("llm") or {}).get("backend", "mock")),
            repeat=int(args.repeat if args.repeat is not None else benchmark_config.get("repeat", 1)),
            output_dir=Path(args.output or benchmark_config.get("output_dir", DEFAULT_RESULTS)),
            config_path=args.config,
        )
        result = run_benchmark(options)
    except RuntimeError as exc:
        backend = _normalize_backend(args.backend or dict(load_runtime_config(args.config).get("llm") or {}).get("backend", "mock"))
        if backend in {"vllm", "openai_compatible", "openai"}:
            print(f"{backend} backend unavailable: {exc}", file=sys.stderr)
            return 1
        raise
    except Exception as exc:
        if _normalize_backend(args.backend or dict(load_runtime_config(args.config).get("llm") or {}).get("backend", "mock")) in {"vllm", "openai_compatible", "openai"}:
            print(f"benchmark failed: {exc}", file=sys.stderr)
            return 1
        raise

    print(f"benchmark output_dir: {result['output_dir']}")
    print(f"summary: {result['summary_csv']}")
    print(f"report: {result['report_md']}")
    return 0


def report_command(args: argparse.Namespace) -> int:
    result = summarize_results(args.results_dir, args.config)
    print(f"summary: {result['summary_csv']}")
    print(f"report: {result['report_md']}")
    return 0


def load_workloads(paths: list[Path] | tuple[Path, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def print_metrics(metrics: dict[str, Any]) -> None:
    keys = [
        "run_id",
        "mode",
        "stage",
        "prompt_tokens",
        "tool_names",
        "raw_tool_tokens",
        "injected_tool_tokens",
        "tool_compression_ratio",
        "latency",
        "ttft",
        "tokens_per_second",
    ]
    for key in keys:
        print(f"{key}: {metrics.get(key, '')}")


def print_config_summary(config_path: Path) -> None:
    config = load_runtime_config(config_path)
    llm = dict(config.get("llm") or {})
    memory = dict(config.get("memory") or {})
    print(f"config: {config_path}")
    print(f"backend: {llm.get('backend', 'mock')}")
    print(f"base_url: {llm.get('base_url', '')}")
    print(f"model: {llm.get('model', '')}")
    print(f"api_key_env: {llm.get('api_key_env', '')}")
    print(f"recent_rounds: {memory.get('recent_rounds', '')}")


def dump_config(config: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore

        return str(yaml.safe_dump(config, allow_unicode=True, sort_keys=False)).rstrip()
    except Exception:
        return json.dumps(config, ensure_ascii=False, indent=2)


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_config(config) + "\n", encoding="utf-8")


def get_nested(config: dict[str, Any], dotted_key: str) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            raise SystemExit(f"missing config key: {dotted_key}")
        current = current[part]
    return current


def set_nested(config: dict[str, Any], dotted_key: str, value: Any) -> None:
    current = config
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        next_value = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            raise SystemExit(f"cannot set nested key under scalar: {part}")
        current = next_value
    current[parts[-1]] = value


def parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def print_tools(json_output: bool = False) -> None:
    registry = build_default_registry(PROJECT_ROOT / "skills")
    tools = sorted(registry.available_tools(), key=lambda item: (-item.priority, item.name))
    rows = [
        {
            "name": tool.name,
            "category": tool.category,
            "priority": tool.priority,
            "permission": tool.permission_level,
            "description": tool.brief_description,
        }
        for tool in tools
    ]
    if json_output:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    print_table(rows, ["name", "category", "priority", "permission", "description"])


def print_tool_detail(name: str, json_output: bool = False) -> int:
    registry = build_default_registry(PROJECT_ROOT / "skills")
    spec = registry.get_tool(name)
    data = {
        "name": spec.name,
        "category": spec.category,
        "priority": spec.priority,
        "permission": spec.permission_level,
        "timeout_seconds": spec.timeout_seconds,
        "max_output_chars": spec.max_output_chars,
        "cacheable": spec.cacheable,
        "tags": spec.tags,
        "description": spec.brief_description,
        "skill_path": spec.skill_path,
    }
    if json_output:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for key, value in data.items():
            print(f"{key}: {value}")
    return 0


def print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        print("no rows")
        return
    widths = {
        column: min(
            max(len(column), *(len(str(row.get(column, ""))) for row in rows)),
            58 if column == "description" else 24,
        )
        for column in columns
    }
    print("  ".join(column.ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        cells = []
        for column in columns:
            text = str(row.get(column, ""))
            if len(text) > widths[column]:
                text = text[: widths[column] - 3] + "..."
            cells.append(text.ljust(widths[column]))
        print("  ".join(cells))


def results_summary(results_dir: Path) -> dict[str, Any]:
    return {
        "results_dir": str(results_dir),
        "tool_results": count_files(results_dir / "tool_store" / "index", "*.json"),
        "csv_files": count_files(results_dir, "*.csv"),
        "reports": count_files(results_dir, "*.md"),
    }


def print_results_summary(results_dir: Path) -> None:
    print(format_results_summary(results_summary(results_dir)))


def format_results_summary(summary: dict[str, Any]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in summary.items())


def count_files(path: Path, pattern: str) -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


def clean_results(results_dir: Path) -> None:
    if not results_dir.exists():
        results_dir.mkdir(parents=True)
    for child in results_dir.iterdir():
        if child.name == "audit_report.md":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for subdir in ["tool_store/raw", "tool_store/index", "tool_store/chunks"]:
        (results_dir / subdir).mkdir(parents=True, exist_ok=True)


def _normalize_backend(backend: str | None) -> str:
    backend = (backend or "mock").replace("-", "_").lower()
    if backend == "openai":
        return "openai_compatible"
    return backend


if __name__ == "__main__":
    raise SystemExit(main())
