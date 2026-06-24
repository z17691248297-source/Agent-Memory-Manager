from __future__ import annotations

import concurrent.futures
import time
from hashlib import sha256
from uuid import uuid4

from agentmem.memory.memory_object import estimate_tokens
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.tools.permissions import permission_allowed
from agentmem.tools.registry import ToolRegistry
from agentmem.tools.result import ToolResult


class ToolExecutor:
    """统一工具执行器，负责权限、超时、异常、缓存和结果外置。"""

    def __init__(
        self,
        registry: ToolRegistry,
        result_store: ToolResultStore,
        allowed_permissions: set[str] | None = None,
    ) -> None:
        self.registry = registry
        self.result_store = result_store
        self.allowed_permissions = allowed_permissions
        self._cache: dict[str, ToolResult] = {}

    def execute(self, tool_name: str, input_text: str, context: dict | None = None) -> ToolResult:
        start = time.perf_counter()
        try:
            spec = self.registry.get_tool(tool_name)
        except KeyError as exc:
            return self._error_result(tool_name, "failed", str(exc), start)

        if not spec.enabled or not permission_allowed(spec.permission_level, self.allowed_permissions):
            return self._error_result(tool_name, "permission_denied", "工具权限不足或已禁用", start)

        cache_key = self._cache_key(tool_name, input_text, context)
        if spec.cacheable and cache_key in self._cache:
            cached = self._cache[cache_key]
            cached.metadata["cache_hit"] = True
            return cached

        try:
            handler = self.registry.get_handler(tool_name)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(handler, input_text, context)
                raw_result = future.result(timeout=spec.timeout_seconds)
            status = "success"
            error = None
        except concurrent.futures.TimeoutError:
            raw_result = ""
            status = "timeout"
            error = f"工具执行超过 {spec.timeout_seconds}s"
        except Exception as exc:  # noqa: BLE001 - 工具边界需要捕获所有异常
            raw_result = ""
            status = "failed"
            error = str(exc)

        if raw_result and len(raw_result) > spec.max_output_chars:
            raw_result = raw_result[: spec.max_output_chars] + "\n[工具输出已被 ToolExecutor 截断]"
            status = "truncated"

        summary = self.result_store.summarize(raw_result, tool_name)
        result = ToolResult(
            result_id=f"{tool_name}_{uuid4().hex[:12]}",
            tool_name=tool_name,
            status=status,
            raw_result=raw_result,
            summary=summary,
            raw_token_len=estimate_tokens(raw_result),
            summary_token_len=estimate_tokens(summary),
            raw_path=None,
            chunks=[],
            latency=time.perf_counter() - start,
            error=error,
            metadata={
                "permission_level": spec.permission_level,
                "cache_hit": False,
                "input_hash": sha256(input_text.encode("utf-8")).hexdigest(),
            },
        )
        saved = self.result_store.save(result)
        if spec.cacheable and status in {"success", "truncated"}:
            self._cache[cache_key] = saved
        return saved

    def _error_result(self, tool_name: str, status: str, error: str, start: float) -> ToolResult:
        summary = f"工具 {tool_name} 执行失败: {error}"
        return ToolResult(
            result_id=f"{tool_name}_{uuid4().hex[:12]}",
            tool_name=tool_name,
            status=status,
            raw_result="",
            summary=summary,
            raw_token_len=0,
            summary_token_len=estimate_tokens(summary),
            raw_path=None,
            chunks=[],
            latency=time.perf_counter() - start,
            error=error,
            metadata={},
        )

    def _cache_key(self, tool_name: str, input_text: str, context: dict | None) -> str:
        payload = f"{tool_name}\n{input_text}\n{context or {}}"
        return sha256(payload.encode("utf-8")).hexdigest()

