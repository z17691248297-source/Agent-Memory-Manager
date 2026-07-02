from __future__ import annotations

import time
import os
from pathlib import Path
from uuid import uuid4

from agentmem.event_memory.memory_delta import MemoryDelta, MemoryDeltaParser
from agentmem.memory.display import prompt_display_tokens
from agentmem.memory.memory_object import estimate_tokens
from agentmem.metrics.gpu_monitor import get_peak_gpu_memory_mb
from agentmem.tools.executor import ToolExecutor
from agentmem.tools.registry import ToolRegistry
from agentmem.tools.router import ToolRouter
from agentmem.vllm.agent_meta import default_segment_type_for_stage
from agentmem.vllm.memory_plan import MemoryPlanLogger


class AgentRuntime:
    """轻量 Agent Runtime：用户输入 -> 工具路由/执行 -> 内存构造 -> LLM。"""

    def __init__(
        self,
        memory,
        tools: ToolRegistry,
        llm_client,
        tool_executor: ToolExecutor | None = None,
        tool_router: ToolRouter | None = None,
        memory_delta_extractor=None,
        max_steps: int = 1,
        enable_next_action_loop: bool = False,
        memory_plan_dir: str | Path | None = None,
    ) -> None:
        self.memory = memory
        self.tools = tools
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.tool_router = tool_router or ToolRouter()
        self.round = 0
        self.memory_delta_parser = MemoryDeltaParser()
        self.memory_delta_extractor = memory_delta_extractor
        self.max_steps = max(1, int(max_steps or 1))
        self.enable_next_action_loop = bool(enable_next_action_loop)
        self.run_id = _memory_session_id(self.memory) or _new_run_id()
        self.memory_plan_logger = MemoryPlanLogger(memory_plan_dir) if memory_plan_dir else None

    def run(self, user_input: str, stage: str = "planning", tool_context: dict | None = None) -> tuple[str, dict]:
        self.round += 1
        tool_context = dict(tool_context or {})
        session_run_id = _memory_session_id(self.memory) or self.run_id
        run_id = session_run_id
        if hasattr(self.memory, "start_round"):
            self.memory.start_round(self.round, stage, user_input, run_id=run_id)
        if hasattr(self.memory, "set_task_requirements"):
            self.memory.set_task_requirements(
                required_facts=tool_context.get("required_facts") or [],
                required_answer_points=tool_context.get("required_answer_points") or [],
            )
        self.memory.add_user_message(user_input)

        decision = self.tool_router.route(user_input, stage, self.tools.available_tools())
        selected_tools = list(decision.selected_tool_names)
        tool_results = []
        prompt_tokens = output_tokens = total_tokens = 0
        latency = ttft = tokens_per_second = 0.0
        assistant_response = ""
        last_agent_meta: dict = {}
        completion_reached = False
        llm_error = ""
        extractor_error = ""
        extractor_calls = 0
        extractor_success_count = 0
        extractor_failure_count = 0
        step_index = 0

        def apply_extractor(assistant_text: str) -> None:
            nonlocal extractor_calls, extractor_error, extractor_success_count, extractor_failure_count
            memory_delta = self._extract_memory_delta(user_input, stage, assistant_text)
            if self.memory_delta_extractor is None:
                return
            extractor_calls += 1
            call_error = str(getattr(self.memory_delta_extractor, "last_error", "") or "")
            if call_error:
                extractor_error = call_error
            if memory_delta.is_empty() or call_error:
                extractor_failure_count += 1
                return
            extractor_success_count += 1
            if hasattr(self.memory, "record_memory_delta"):
                self.memory.record_memory_delta(memory_delta)

        if self.tool_executor and selected_tools and not self.enable_next_action_loop:
            for tool_name in selected_tools:
                result = self._execute_tool(tool_name, user_input, stage, tool_results, tool_context)
                if result.status in {"failed", "timeout", "permission_denied"}:
                    completion_reached = True
                    break

        max_llm_steps = self.max_steps if self.enable_next_action_loop else 1
        for step_index in range(1, max_llm_steps + 1):
            messages = self.memory.build_messages(stage=stage, selected_tools=selected_tools)
            segment_type = _segment_type_for_runtime_stage(stage, bool(tool_results), bool(selected_tools))
            agent_meta_context_id = f"{run_id}:round_{self.round}:step_{step_index}:{stage}:{segment_type}"
            agent_meta_tool_name = selected_tools[0] if segment_type == "tool_result" and selected_tools else None
            agent_meta_priority = _priority_for_runtime_stage(stage, segment_type)
            planned_agent_meta = self._build_agent_meta(
                run_id=run_id,
                stage=stage,
                segment_type=segment_type,
                context_id=agent_meta_context_id,
                tool_name=agent_meta_tool_name,
                priority=agent_meta_priority,
            )
            self._record_memory_plan(
                run_id=run_id,
                stage=stage,
                context_id=agent_meta_context_id,
                segment_type=segment_type,
                priority=agent_meta_priority,
                ttl=planned_agent_meta.get("ttl") if planned_agent_meta else None,
                messages=messages,
                selected_tools=selected_tools,
                tool_results=tool_results,
                agent_meta=planned_agent_meta,
            )
            try:
                response = self.llm_client.chat(
                    messages,
                    agent_meta=planned_agent_meta,
                    run_id=run_id,
                    stage=stage,
                    segment_type=segment_type,
                    context_id=agent_meta_context_id,
                    tool_name=agent_meta_tool_name,
                    priority=agent_meta_priority,
                )
            except RuntimeError as exc:
                llm_error = str(exc)
                prompt_tokens += estimate_tokens(str(messages))
                assistant_response = f"LLM call failed: {llm_error}"
                self.memory.add_assistant_message(assistant_response)
                completion_reached = True
                break
            prompt_tokens += int(response.get("prompt_tokens", 0) or 0)
            output_tokens += int(response.get("completion_tokens", 0) or 0)
            total_tokens += int(response.get("total_tokens", 0) or 0)
            latency += float(response.get("latency", 0.0) or 0.0)
            if response.get("agent_meta_sent"):
                last_agent_meta = dict(response.get("agent_meta") or {})
            if step_index == 1:
                ttft = float(response.get("ttft", -1) or -1)
            tokens_per_second = float(response.get("tokens_per_second", -1) or -1)

            parsed = self.memory_delta_parser.parse(response.get("content", ""))
            assistant_response = parsed.assistant_response
            next_action = parsed.next_action or {}

            force_tool_after_draft = (
                self.enable_next_action_loop
                and stage == "tool_calling"
                and step_index == 1
                and selected_tools
                and not tool_results
                and _is_final_action(next_action)
            )
            if force_tool_after_draft:
                result = self._execute_tool(selected_tools[0], user_input, stage, tool_results, tool_context)
                if result.status not in {"failed", "timeout", "permission_denied"}:
                    apply_extractor("")
                    continue
                completion_reached = True
                break

            self.memory.add_assistant_message(assistant_response)
            memory_delta = parsed.memory_delta
            if memory_delta.is_empty():
                should_extract = not (
                    self.enable_next_action_loop
                    and stage == "tool_calling"
                    and selected_tools
                    and not tool_results
                )
                if should_extract:
                    apply_extractor(assistant_response)
            elif hasattr(self.memory, "record_memory_delta"):
                self.memory.record_memory_delta(memory_delta)

            if not self.enable_next_action_loop or _is_final_action(next_action):
                completion_reached = True
                break
            if str(next_action.get("type", "")).lower() != "tool_call":
                completion_reached = True
                break
            tool_name = str(next_action.get("tool") or next_action.get("name") or "")
            if not tool_name:
                completion_reached = True
                break
            result = self._execute_tool(tool_name, _tool_input_from_action(next_action, user_input), stage, tool_results, tool_context)
            selected_tools = [tool_name]
            if result.status in {"failed", "timeout", "permission_denied"}:
                self.memory.add_assistant_message(f"Tool call failed: {tool_name} status={result.status}")
                if hasattr(self.memory, "record_memory_delta"):
                    self.memory.record_memory_delta(
                        MemoryDelta(
                            warnings=[
                                f"Tool call failed: {tool_name} status={result.status} error={result.error or ''}".strip()
                            ]
                        )
                    )
                completion_reached = True
                break
            apply_extractor("")

        if not completion_reached and assistant_response:
            self.memory.add_assistant_message("Max agent steps reached; returning latest assistant response.")
        hint = self.memory.latest_metrics_hint()
        round_raw_tool_tokens = sum(result.raw_token_len for result in tool_results)
        uses_tool_externalization = bool(getattr(self.memory, "enable_tool_externalization", False))
        round_injected_tool_tokens = (
            sum(result.summary_token_len for result in tool_results)
            if uses_tool_externalization
            else sum(prompt_display_tokens(result, estimate_tokens) for result in tool_results)
        )
        round_ratios = [result.compression_ratio for result in tool_results if result.raw_token_len > 0]
        round_tool_compression_ratio = (
            (sum(round_ratios) / len(round_ratios) if round_ratios else 1.0)
            if uses_tool_externalization
            else 1.0
        )
        structural_success = bool(assistant_response.strip()) and not llm_error and all(
            result.status not in {"failed", "timeout", "permission_denied"} for result in tool_results
        )

        metrics = {
            "run_id": run_id,
            "round": self.round,
            "mode": self.memory.mode,
            "stage": stage,
            "model": getattr(self.llm_client, "model", ""),
            "prompt_tokens": prompt_tokens,
            "system_tokens": hint.get("system", 0),
            "tool_schema_tokens": hint.get("tool_schema", 0),
            "tool_brief_tokens": hint.get("tool_brief", 0),
            "loaded_skill_tokens": hint.get("loaded_skill_tokens", 0),
            "loaded_skill_names": ",".join(hint.get("loaded_skill_names", [])),
            "tool_names": ",".join(result.tool_name for result in tool_results),
            "route_reason": "; ".join(
                f"{name}:{reason}" for name, reason in decision.route_reason.items()
            ),
            "history_tokens": hint.get("history", 0),
            "summary_tokens": hint.get("summary", 0),
            "tool_summary_tokens": hint.get("tool_summary", 0),
            "branch_tokens": hint.get("branch", 0),
            "raw_tool_tokens": round_raw_tool_tokens,
            "injected_tool_tokens": round_injected_tool_tokens,
            "tool_compression_ratio": round_tool_compression_ratio,
            "latency": latency + sum(result.latency for result in tool_results),
            "ttft": ttft,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens or (prompt_tokens + output_tokens),
            "tokens_per_second": tokens_per_second,
            "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
            "success": structural_success,
            "agent_steps": max_llm_steps if not completion_reached else min(max_llm_steps, step_index),
            "llm_error": llm_error,
            "extractor_calls": extractor_calls,
            "extractor_error": extractor_error,
            "extractor_success_count": extractor_success_count,
            "extractor_failure_count": extractor_failure_count,
            "extractor_effective": bool(extractor_success_count > 0),
            "extractor_status": "active" if extractor_success_count > 0 else ("fallback" if extractor_calls else "not_used"),
            "agent_meta_enabled": bool(getattr(self.llm_client, "enable_agent_meta", False)),
            "agent_id": last_agent_meta.get("agent_id", os.getenv("AGENTMEM_AGENT_ID", "")),
            "agent_meta_sent": bool(last_agent_meta),
            "agent_meta_agent_id": last_agent_meta.get("agent_id", ""),
            "agent_meta_session_id": last_agent_meta.get("session_id", ""),
            "agent_meta_context_id": last_agent_meta.get("context_id", ""),
            "agent_meta_segment_type": last_agent_meta.get("segment_type", ""),
            "agent_meta_priority": last_agent_meta.get("priority", ""),
        }
        if hasattr(self.memory, "record_metrics"):
            self.memory.record_metrics(metrics)
            final_hint = self.memory.latest_metrics_hint()
            for key in [
                "full_history_tokens",
                "state_view_tokens",
                "event_count",
                "memory_delta_count",
                "fact_count",
                "decision_count",
                "artifact_ref_count",
                "snapshot_count",
                "memory_run_id",
            ]:
                if key in final_hint:
                    metrics[key] = final_hint[key]
        return assistant_response, metrics

    def _extract_memory_delta(self, user_input: str, stage: str, assistant_response: str) -> MemoryDelta:
        if self.memory_delta_extractor is None or not hasattr(self.memory, "build_extractor_payload"):
            return MemoryDelta()
        payload = self.memory.build_extractor_payload(
            current_query=user_input,
            stage=stage,
            assistant_response=assistant_response,
        )
        return self.memory_delta_extractor.extract_memory_delta(payload)

    def _execute_tool(self, tool_name: str, input_text: str, stage: str, tool_results: list, tool_context: dict | None = None) -> object:
        if hasattr(self.memory, "record_tool_call"):
            self.memory.record_tool_call(tool_name, input_text, stage)
        start = time.perf_counter()
        context = {"stage": stage, **dict(tool_context or {})}
        result = self.tool_executor.execute(tool_name, input_text, context=context) if self.tool_executor else None
        if result is None:
            raise RuntimeError("tool_executor is not configured")
        self.memory.add_tool_result(result)
        tool_results.append(result)
        result.latency = time.perf_counter() - start
        return result

    def _build_agent_meta(
        self,
        *,
        run_id: str,
        stage: str,
        segment_type: str,
        context_id: str,
        tool_name: str | None,
        priority: str | None,
    ) -> dict:
        if not hasattr(self.llm_client, "build_agent_meta"):
            return {}
        meta = self.llm_client.build_agent_meta(
            run_id=run_id,
            stage=stage,
            segment_type=segment_type,
            context_id=context_id,
            tool_name=tool_name,
            priority=priority,
        )
        return dict(meta or {})

    def _record_memory_plan(
        self,
        *,
        run_id: str,
        stage: str,
        context_id: str,
        segment_type: str,
        priority: str | None,
        ttl: int | None,
        messages: list[dict[str, str]],
        selected_tools: list[str],
        tool_results: list,
        agent_meta: dict,
    ) -> None:
        if self.memory_plan_logger is None:
            return
        hint = self.memory.latest_metrics_hint() if hasattr(self.memory, "latest_metrics_hint") else {}
        included_items = _included_plan_items(stage, selected_tools, tool_results, hint)
        external_refs = [
            {
                "tool_name": getattr(result, "tool_name", ""),
                "result_id": getattr(result, "result_id", ""),
                "summary_token_len": int(getattr(result, "summary_token_len", 0) or 0),
            }
            for result in tool_results
        ]
        raw_tool_tokens = sum(int(getattr(result, "raw_token_len", 0) or 0) for result in tool_results)
        injected_tool_tokens = sum(
            int(getattr(result, "summary_token_len", 0) or 0)
            if bool(getattr(self.memory, "enable_tool_externalization", False))
            else prompt_display_tokens(result, estimate_tokens)
            for result in tool_results
        )
        excluded_items = ["raw_tool_result_body"] if raw_tool_tokens > injected_tool_tokens else []
        self.memory_plan_logger.record(
            run_id=run_id,
            stage=stage,
            context_id=context_id,
            segment_type=segment_type,
            priority=priority,
            ttl=ttl,
            included_items=included_items,
            external_refs=external_refs,
            excluded_items=excluded_items,
            estimated_prompt_tokens=estimate_tokens(str(messages)),
            estimated_saved_tokens=max(0, raw_tool_tokens - injected_tool_tokens),
            agent_meta=agent_meta,
        )


def _is_final_action(action: dict) -> bool:
    if not action:
        return True
    return str(action.get("type", "")).lower() in {"", "final", "finish", "none"}


def _tool_input_from_action(action: dict, fallback: str) -> str:
    args = action.get("args")
    if isinstance(args, dict):
        for key in ["input", "query", "text", "expression", "path"]:
            value = args.get(key)
            if value not in {None, ""}:
                return str(value)
        return str(args) if args else fallback
    if args not in {None, ""}:
        return str(args)
    return fallback


def _new_run_id() -> str:
    return f"run_{int(time.time() * 1000)}_{uuid4().hex[:8]}"


def _memory_session_id(memory) -> str:
    return str(getattr(memory, "run_id", "") or getattr(memory, "session_id", "") or "")


def _segment_type_for_runtime_stage(stage: str, has_tool_results: bool, has_selected_tools: bool = False) -> str:
    if has_tool_results:
        return "tool_result"
    if stage == "tool_calling" and has_selected_tools:
        return "tool_schema"
    return default_segment_type_for_stage(stage)


def _priority_for_runtime_stage(stage: str, segment_type: str) -> str | None:
    if segment_type in {"shared_prefix", "system", "tool_schema"}:
        return "high"
    if stage == "reflection":
        return "low"
    if stage == "planning":
        return "normal"
    return None


def _included_plan_items(stage: str, selected_tools: list[str], tool_results: list, hint: dict) -> list[dict[str, object]]:
    items: list[dict[str, object]] = [{"name": "stage", "value": stage}]
    for key in ["system", "tool_schema", "tool_brief", "history", "summary", "tool_summary", "state_view"]:
        value = int(hint.get(key, 0) or 0)
        if value > 0:
            items.append({"name": key, "estimated_tokens": value})
    if selected_tools:
        items.append({"name": "selected_tools", "value": ",".join(selected_tools)})
    if tool_results:
        items.append({"name": "tool_results", "count": len(tool_results)})
    return items
