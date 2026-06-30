from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agentmem.memory.memory_object import estimate_tokens
from agentmem.tools.log_analyzer import generate_original_tool_heavy_log


TASK_FILE = PROJECT_ROOT / "benchmarks" / "tasks" / "tool_heavy.jsonl"
OUTPUT_FILE = PROJECT_ROOT / "benchmarks" / "fixtures" / "tool_heavy_scaled.log"
# The lightweight local estimator undercounts Qwen tokenizer tokens on this
# synthetic log by roughly 2x. Keep the fixture near 6.5K local-estimated tokens
# so the full baseline prompt lands below a 16K server-side limit.
TARGET_BASELINE_PROMPT_SIZE = 6_100
CONTEXT_LINES = 3


def main() -> int:
    task = _load_tool_heavy_task()
    required_facts = [str(item) for item in task.get("required_facts") or []]
    original = generate_original_tool_heavy_log()
    original_lines = original.splitlines()
    selected = _select_lines(original_lines, required_facts)
    scaled_text = "\n".join(original_lines[index] for index in selected)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(scaled_text, encoding="utf-8")

    matched = [
        fact
        for fact in required_facts
        if any(fact.lower() in line.lower() for line in scaled_text.splitlines())
    ]
    stats = {
        "original_lines": len(original_lines),
        "new_lines": len(selected),
        "original_chars": len(original),
        "new_chars": len(scaled_text),
        "estimated_baseline_prompt_size": estimate_tokens(scaled_text),
        "required_facts": required_facts,
        "matched_required_facts": matched,
        "output_file": str(OUTPUT_FILE.relative_to(PROJECT_ROOT)),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def _load_tool_heavy_task() -> dict:
    for line in TASK_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            return json.loads(line)
    raise ValueError(f"empty task file: {TASK_FILE}")


def _select_lines(lines: list[str], required_facts: list[str]) -> list[int]:
    required_indexes: set[int] = set()
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(fact.lower() in lowered for fact in required_facts):
            for context_index in range(max(0, index - CONTEXT_LINES), min(len(lines), index + CONTEXT_LINES + 1)):
                required_indexes.add(context_index)

    selected: set[int] = set(required_indexes)
    filler_candidates = [
        index
        for index, line in enumerate(lines)
        if index not in selected and " INFO " in f" {line} "
    ]
    if not filler_candidates:
        return sorted(selected)

    step = max(1, len(filler_candidates) // 1050)
    for index in filler_candidates[::step]:
        selected.add(index)
        if _estimated_selected_tokens(lines, selected) >= TARGET_BASELINE_PROMPT_SIZE:
            break
    return sorted(selected)


def _estimated_selected_tokens(lines: list[str], selected: set[int]) -> int:
    return estimate_tokens("\n".join(lines[index] for index in sorted(selected)))


if __name__ == "__main__":
    raise SystemExit(main())
