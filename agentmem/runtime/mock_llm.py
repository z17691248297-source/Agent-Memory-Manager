from __future__ import annotations

import json
import time

from agentmem.memory.memory_object import estimate_tokens


class MockLLMClient:
    """无模型、无 GPU 环境下的固定响应后端。"""

    model = "local-test"

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> dict:
        start = time.perf_counter()
        prompt = "\n".join(message.get("content", "") for message in messages)
        prompt_tokens = estimate_tokens(prompt)
        lower_prompt = prompt.lower()

        # Keep test answers deterministic while exposing the same signals that
        # task evaluators check on a real backend.
        if "constraint_alpha_001" in lower_prompt:
            content = "constraint_alpha_001：AgentMem 必须优先进行工具结果外置，并保留任务成功率。"
        elif all(keyword in lower_prompt for keyword in ["baseline", "optimized"]) and (
            "success rate" in lower_prompt or "任务成功率" in prompt
        ):
            content = (
                "结论：baseline 会放大 prompt；optimized 通过工具结果外置、历史摘要和 stable prefix "
                "降低上下文压力。日志证据包含 OOM、timeout、KV cache 问题，success rate 需要由 evaluator 统计。"
            )
        elif any(keyword in lower_prompt for keyword in ["oom", "timeout", "kv cache"]):
            content = "日志结论：发现 CUDA OOM、timeout 和 KV cache allocation failed，建议外置工具结果并降低 prefill 压力。"
        elif all(keyword in lower_prompt for keyword in ["baseline", "optimized"]):
            content = "baseline 注入完整上下文；optimized 使用工具结果外置、历史摘要和 stable prefix 控制 prompt tokens。"
        elif "方案" in prompt and ("优点" in prompt or "风险" in prompt):
            content = "方案一：工具结果外置。优点是降低注入 tokens，风险是需要 result_id 回查。方案二：历史摘要。优点是控制长会话，风险是摘要遗漏。"
        elif "工具结果" in prompt or "result_id" in prompt:
            content = "已基于工具摘要、result_id 和上下文生成回答。"
        elif "计算" in prompt:
            content = "已完成计算任务。"
        else:
            content = "已根据当前上下文生成简要回答。"
        payload = {
            "assistant_response": content,
            "next_action": _next_action(prompt),
            "memory_delta": _memory_delta(prompt, content),
        }
        output = json.dumps(payload, ensure_ascii=False)
        completion_tokens = estimate_tokens(output)
        return {
            "content": output,
            "latency": time.perf_counter() - start,
            "ttft": 0.0,
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "tokens_per_second": -1,
        }


def _memory_delta(prompt: str, content: str) -> dict:
    facts = []
    lower = prompt.lower()
    for token in _interesting_phrases(prompt):
        facts.append({"content": token, "source": "local_test_llm", "confidence": 0.8, "importance": 0.7})
    if "result_id" in lower or "tool" in lower or "工具" in prompt:
        facts.append({"content": "工具结果应通过 result_id 和 artifact reference 管理", "source": "local_test_llm", "confidence": 0.8, "importance": 0.7})
    decisions = []
    if any(word in content for word in ["结论", "建议", "必须"]):
        decisions.append({"content": content[:240], "reason": "assistant response", "confidence": 0.75, "source": "local_test_llm"})
    return {
        "goals": _goals(prompt),
        "constraints": _constraints(prompt),
        "facts": facts[:12],
        "decisions": decisions,
        "open_questions": [],
        "todos": [],
        "artifact_refs": [],
        "tool_summaries": [],
        "warnings": [],
    }


def _next_action(prompt: str) -> dict | None:
    lower = prompt.lower()
    intent = _intent_text(prompt)
    lower_intent = intent.lower()
    has_artifact = "result_id:" in lower or "artifact references:" in lower and "result_id=" in lower
    if has_artifact:
        return None
    if "## calculator" in prompt or '"name": "calculator"' in prompt:
        if "计算" in intent or "calculate" in lower_intent or any(op in intent for op in ["+", "-", "*", "/"]):
            return {"type": "tool_call", "tool": "calculator", "args": {"input": intent or "calculate requested expression"}}
    if "## log_analyzer" in prompt or '"name": "log_analyzer"' in prompt:
        if any(term in lower_intent for term in ["log", "日志", "oom", "timeout", "kv cache"]):
            return {"type": "tool_call", "tool": "log_analyzer", "args": {"input": intent or "analyze requested log artifact"}}
    return None


def _intent_text(prompt: str) -> str:
    marker = "Current Query:"
    if marker in prompt:
        return prompt.rsplit(marker, 1)[-1].strip()
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    return lines[-1] if lines else prompt


def _goals(prompt: str) -> list[str]:
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    return [line[:240] for line in lines if any(marker in line for marker in ["目标", "请分析", "请判断", "最后给出"])][:3]


def _constraints(prompt: str) -> list[str]:
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    return [line[:240] for line in lines if any(marker in line for marker in ["必须", "要求", "关注", "保留", "覆盖", "记录"])][:8]


def _interesting_phrases(prompt: str) -> list[str]:
    phrases = []
    candidates = [
        "AgentMem",
        "Event-Sourced Memory",
        "工具结果外置",
        "result_id",
        "artifact",
        "历史摘要",
        "stable prefix",
        "benchmark",
        "vLLM",
        "Qwen",
        "MiniCPM",
        "baseline",
        "optimized",
        "prompt_tokens",
        "CUDA OOM",
        "OOM",
        "timeout",
        "KV cache",
        "success rate",
        "任务成功率",
    ]
    lower = prompt.lower()
    for candidate in candidates:
        if candidate.lower() in lower:
            phrases.append(candidate)
    return phrases
