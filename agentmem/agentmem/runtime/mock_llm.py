from __future__ import annotations

import time

from agentmem.memory.memory_object import estimate_tokens


class MockLLMClient:
    """无模型、无 GPU 环境下的固定响应后端。"""

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

        # Keep mock answers deterministic while exposing the same signals that
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
        completion_tokens = estimate_tokens(content)
        return {
            "content": content,
            "latency": time.perf_counter() - start,
            "ttft": 0.0,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "tokens_per_second": -1,
        }
