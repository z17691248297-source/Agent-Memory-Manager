from __future__ import annotations

from copy import deepcopy
import multiprocessing
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
            cached = deepcopy(self._cache[cache_key])
            cached.metadata["cache_hit"] = True
            cached.latency = time.perf_counter() - start
            return cached

        handler = self.registry.get_handler(tool_name)
        status, raw_result, error = _execute_in_process(
            handler,
            input_text,
            context,
            timeout_seconds=float(spec.timeout_seconds),
        )

        display_truncated = bool(raw_result and len(raw_result) > spec.max_output_chars)

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
                "display_truncated": display_truncated,
                "display_max_output_chars": spec.max_output_chars,
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


def _execute_in_process(handler, input_text: str, context: dict | None, timeout_seconds: float) -> tuple[str, str, str | None]:
    start_methods = multiprocessing.get_all_start_methods()
    method = "fork" if "fork" in start_methods else start_methods[0]
    process_context = multiprocessing.get_context(method)
    receive, send = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_tool_process_entry,
        args=(send, handler, input_text, context),
        daemon=True,
    )
    process.start()
    send.close()
    deadline = time.monotonic() + max(0.001, timeout_seconds)
    payload: tuple[str, str] | None = None
    try:
        while time.monotonic() < deadline:
            wait = min(0.02, max(0.0, deadline - time.monotonic()))
            if receive.poll(wait):
                payload = receive.recv()
                break
            if not process.is_alive():
                break
        if payload is None and receive.poll():
            payload = receive.recv()
        if payload is None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=0.2)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(timeout=0.2)
            return "timeout", "", f"工具执行超过 {timeout_seconds:g}s"
        status, value = payload
        process.join(timeout=0.2)
        if status == "success":
            return "success", value, None
        return "failed", "", value
    finally:
        receive.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.2)


def _tool_process_entry(send, handler, input_text: str, context: dict | None) -> None:
    try:
        result = handler(input_text, context)
        send.send(("success", str(result)))
    except BaseException as exc:  # noqa: BLE001 - child process must report all failures
        send.send(("failed", str(exc)))
    finally:
        send.close()
