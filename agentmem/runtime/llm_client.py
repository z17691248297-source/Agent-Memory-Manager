from __future__ import annotations

import time
from typing import Any

from agentmem.memory.memory_object import estimate_tokens
from agentmem.vllm.agent_meta import AgentMetaBuilder, default_segment_type_for_stage


class OpenAICompatibleClient:
    """通用 OpenAI-compatible Chat Completions 客户端。

    既可以连接本地 vLLM，也可以连接模型厂商提供的 OpenAI-compatible API。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "EMPTY",
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        temperature: float = 0.2,
        max_tokens: int = 512,
        timeout: float = 120,
        stream: bool = False,
        max_retries: int = 2,
        extra_body: dict[str, Any] | None = None,
        backend: str = "openai_compatible",
        enable_agent_meta: bool = False,
        agent_meta_builder: AgentMetaBuilder | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.stream = stream
        self.max_retries = max(0, int(max_retries))
        self.extra_body = dict(extra_body or {})
        self.backend = str(backend).replace("-", "_").lower()
        self.enable_agent_meta = bool(enable_agent_meta)
        self.agent_meta_builder = agent_meta_builder

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        agent_meta: dict[str, Any] | None = None,
        run_id: str | None = None,
        stage: str = "planning",
        segment_type: str | None = None,
        context_id: str | None = None,
        source: str = "agentmem",
        tool_name: str | None = None,
        priority: str | None = None,
        ttl: int | None = None,
        branch_id: str | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 openai 包，请安装 requirements.txt") from exc

        client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )
        request_temperature = self.temperature if temperature is None else temperature
        request_max_tokens = self.max_tokens if max_tokens is None else max_tokens
        effective_agent_meta = self._resolve_agent_meta(
            agent_meta=agent_meta,
            run_id=run_id,
            stage=stage,
            segment_type=segment_type,
            context_id=context_id,
            source=source,
            tool_name=tool_name,
            priority=priority,
            ttl=ttl,
            branch_id=branch_id,
        )
        try:
            if self.stream:
                return self._chat_streaming(
                    client,
                    messages,
                    temperature=request_temperature,
                    max_tokens=request_max_tokens,
                    start=start,
                    agent_meta=effective_agent_meta,
                )
            request_kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": request_temperature,
                "max_tokens": request_max_tokens,
            }
            extra_body = self._request_extra_body(effective_agent_meta)
            if extra_body:
                request_kwargs["extra_body"] = extra_body
            response = client.chat.completions.create(
                **request_kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "调用 OpenAI-compatible API 失败: "
                f"base_url={self.base_url}, model={self.model}, "
                f"agent_meta_enabled={self.enable_agent_meta}, "
                f"agent_meta_sent={bool(effective_agent_meta)}, error={exc}"
            ) from exc

        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) or estimate_tokens(str(messages))
        completion_tokens = getattr(usage, "completion_tokens", None) or estimate_tokens(content)
        return {
            "content": content,
            "latency": time.perf_counter() - start,
            "ttft": -1,
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "tokens_per_second": _tokens_per_second(completion_tokens, time.perf_counter() - start),
            "agent_meta_sent": bool(effective_agent_meta),
            "agent_meta": effective_agent_meta or {},
        }

    def _chat_streaming(
        self,
        client: Any,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        start: float,
        agent_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        extra_body = self._request_extra_body(agent_meta)
        if extra_body:
            request_kwargs["extra_body"] = extra_body
        if self.base_url:
            request_kwargs["stream_options"] = {"include_usage": True}
        chunks = client.chat.completions.create(
            **request_kwargs,
        )
        first_token_time: float | None = None
        content_parts: list[str] = []
        usage_prompt_tokens: int | None = None
        usage_completion_tokens: int | None = None
        for chunk in chunks:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                usage_prompt_tokens = getattr(usage, "prompt_tokens", None) or usage_prompt_tokens
                usage_completion_tokens = getattr(usage, "completion_tokens", None) or usage_completion_tokens
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None) or ""
            if text and first_token_time is None:
                first_token_time = time.perf_counter()
            if text:
                content_parts.append(text)
        latency = time.perf_counter() - start
        content = "".join(content_parts)
        prompt_tokens = usage_prompt_tokens or estimate_tokens(str(messages))
        completion_tokens = usage_completion_tokens or estimate_tokens(content)
        return {
            "content": content,
            "latency": latency,
            "ttft": (first_token_time - start) if first_token_time is not None else -1,
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "tokens_per_second": _tokens_per_second(completion_tokens, latency),
            "agent_meta_sent": bool(agent_meta),
            "agent_meta": agent_meta or {},
        }

    def _resolve_agent_meta(
        self,
        *,
        agent_meta: dict[str, Any] | None,
        run_id: str | None,
        stage: str,
        segment_type: str | None,
        context_id: str | None,
        source: str,
        tool_name: str | None,
        priority: str | None,
        ttl: int | None,
        branch_id: str | None,
    ) -> dict[str, Any] | None:
        if self.backend != "vllm" or not self.enable_agent_meta:
            return None
        if agent_meta is not None:
            return dict(agent_meta)
        if self.agent_meta_builder is None:
            return None
        return self.agent_meta_builder.build(
            run_id=str(run_id or "agentmem_session"),
            stage=stage,
            segment_type=segment_type or default_segment_type_for_stage(stage),
            context_id=context_id,
            source=source,
            tool_name=tool_name,
            priority=priority,
            ttl=ttl,
            branch_id=branch_id,
        )

    def build_agent_meta(
        self,
        *,
        agent_meta: dict[str, Any] | None = None,
        run_id: str | None = None,
        stage: str = "planning",
        segment_type: str | None = None,
        context_id: str | None = None,
        source: str = "agentmem",
        tool_name: str | None = None,
        priority: str | None = None,
        ttl: int | None = None,
        branch_id: str | None = None,
    ) -> dict[str, Any] | None:
        return self._resolve_agent_meta(
            agent_meta=agent_meta,
            run_id=run_id,
            stage=stage,
            segment_type=segment_type,
            context_id=context_id,
            source=source,
            tool_name=tool_name,
            priority=priority,
            ttl=ttl,
            branch_id=branch_id,
        )

    def _request_extra_body(self, agent_meta: dict[str, Any] | None) -> dict[str, Any] | None:
        extra_body = dict(self.extra_body)
        if agent_meta is not None:
            extra_body["agent_meta"] = agent_meta
        return extra_body or None


def _tokens_per_second(completion_tokens: int, latency: float) -> float:
    if latency <= 0:
        return -1
    return completion_tokens / latency
