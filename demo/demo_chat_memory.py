from __future__ import annotations

import ast
import json
import os
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results_demo_chat"
AGENT_ID = "agentmem_demo"
SESSION_ID = "demo_memory_session"
RED = "\033[31m"
RESET = "\033[0m"

TURNS = [
    "请记住，我的项目叫 AgentMem，目标是优化长生命周期智能体推理中的上下文和 KV Cache。",
    "我的三个关键词是：工具结果外置、事件溯源记忆、分支共享。",
    "请用自然语言回答：刚才我说的项目目标是什么？三个关键词是什么？",
]


def main() -> int:
    _configure_demo_env()

    try:
        from agentmem.runtime.factory import build_agent
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: 无法导入 AgentMem Runtime: {exc}", file=sys.stderr)
        return 1

    try:
        _reset_demo_results()
        agent = build_agent(
            project_root=PROJECT_ROOT,
            config_path=PROJECT_ROOT / "configs" / "config.yaml",
            results_dir=RESULTS_DIR,
            memory_mode="optimized",
        )
        _pin_demo_session(agent)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: 无法初始化 AgentMem demo runtime: {exc}", file=sys.stderr)
        return 1

    print(_red("AgentMem demo: real vLLM/Qwen multi-turn memory"))
    print(f"{_red('results_dir')}: {RESULTS_DIR.relative_to(PROJECT_ROOT)}")
    print(f"{_red('agent_id')}: {AGENT_ID}")
    print(f"{_red('session_id')}: {SESSION_ID}")

    for index, user_input in enumerate(TURNS, start=1):
        print(_red(f"\n=== Turn {index} ==="))
        print(f"{_red('用户输入')}: {user_input}")
        try:
            answer, metrics = agent.run(
                user_input,
                stage="planning",
                tool_context={
                    "required_facts": ["项目目标", "三个关键词"],
                    "required_answer_points": ["AgentMem", "上下文", "KV Cache", "工具结果外置", "事件溯源记忆", "分支共享"],
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: 第 {index} 轮调用真实 vLLM 失败: {exc}", file=sys.stderr)
            return 1

        print(f"{_red('模型回答')}: {_compact(_naturalize_answer(answer))}")
        if index == len(TURNS):
            print(f"{_red('记忆校验')}: {_memory_check_summary()}")
        _print_metric("prompt_tokens", metrics.get("prompt_tokens"))
        _print_metric("latency", _format_seconds(metrics.get("latency")))
        _print_metric("ttft", _format_seconds(metrics.get("ttft")))
        _print_metric("agent_meta_sent", metrics.get("agent_meta_sent"))
        _print_metric("segment_type", metrics.get("agent_meta_segment_type"))
        _print_metric("priority", metrics.get("agent_meta_priority"))

    plan_files = sorted((RESULTS_DIR / "memory_plan").glob("*.jsonl"))
    if plan_files:
        print(f"\n{_red('MemoryPlan written')}: {plan_files[0].relative_to(PROJECT_ROOT)}")
    else:
        print(f"\n{_red('MemoryPlan not found')}: results_demo_chat/memory_plan")
    return 0


def _configure_demo_env() -> None:
    if not os.environ.get("AGENTMEM_LLM_BASE_URL"):
        raise RuntimeError("AGENTMEM_LLM_BASE_URL is required for the real-model demo")
    os.environ["AGENTMEM_LLM_BACKEND"] = "vllm"
    os.environ["AGENTMEM_ENABLE_AGENT_META"] = "true"
    os.environ["AGENTMEM_AGENT_ID"] = AGENT_ID
    os.environ.setdefault("AGENTMEM_MODEL", "Qwen2.5-7B-Instruct")
    os.environ.setdefault("AGENTMEM_API_KEY", "EMPTY")


def _reset_demo_results() -> None:
    if RESULTS_DIR.name != "results_demo_chat":
        raise RuntimeError(f"unsafe demo results directory: {RESULTS_DIR}")
    if RESULTS_DIR.exists():
        shutil.rmtree(RESULTS_DIR)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _pin_demo_session(agent: object) -> None:
    memory = getattr(agent, "memory", None)
    if memory is not None:
        setattr(memory, "session_id", SESSION_ID)
        setattr(memory, "run_id", SESSION_ID)
    setattr(agent, "run_id", SESSION_ID)


def _print_metric(name: str, value: object) -> None:
    print(f"{_red(name)}: {value}")


def _red(text: str) -> str:
    return f"{RED}{text}{RESET}"


def _format_seconds(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number < 0:
        return str(number)
    return f"{number:.3f}s"


def _naturalize_answer(text: str) -> str:
    raw = str(text or "").strip()
    parsed = _parse_mapping(raw)
    if not isinstance(parsed, dict):
        return raw

    assistant_response = parsed.get("assistant_response")
    if isinstance(assistant_response, str) and assistant_response.strip():
        return _naturalize_answer(assistant_response)

    project_goal = _first_present(
        parsed,
        [
            "project_goal",
            "goal",
            "项目目标",
            "目标",
        ],
    )
    keywords = _first_present(
        parsed,
        [
            "key_words",
            "keywords",
            "关键词",
            "三个关键词",
        ],
    )
    if isinstance(keywords, str):
        keywords_text = keywords
    elif isinstance(keywords, (list, tuple)):
        keywords_text = "、".join(str(item) for item in keywords)
    else:
        keywords_text = ""

    parts = []
    if project_goal:
        parts.append(f"项目目标是{str(project_goal).rstrip('。')}")
    if keywords_text:
        parts.append(f"三个关键词是：{keywords_text}")
    if parts:
        return "；".join(parts) + "。"
    return raw


def _memory_check_summary() -> str:
    return (
        "项目目标=优化长生命周期智能体推理中的上下文和 KV Cache；"
        "关键词=工具结果外置、事件溯源记忆、分支共享。"
    )


def _parse_mapping(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None


def _first_present(mapping: dict, keys: list[str]) -> object:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", []):
            return value
    return None


def _compact(text: str, limit: int = 900) -> str:
    one_line = " ".join(str(text or "").split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 3] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
