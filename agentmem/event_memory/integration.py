from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from agentmem.event_memory.event import AgentEvent
from agentmem.event_memory.event_log import EventLog
from agentmem.event_memory.evidence import ArtifactContextManager
from agentmem.event_memory.memory_delta import MemoryDelta
from agentmem.event_memory.projector import MemoryProjector
from agentmem.event_memory.renderer import MemoryViewRenderer
from agentmem.event_memory.schema import TaskStateView
from agentmem.event_memory.snapshot import MemorySnapshotStore
from agentmem.memory.memory_object import estimate_tokens
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.tools.registry import ToolRegistry
from agentmem.tools.result import ToolResult


class EventSourcedMemoryAdapter:
    """Memory implementation backed by an event log and projected state view."""

    def __init__(
        self,
        system_prompt: str,
        tool_registry: ToolRegistry,
        result_store: ToolResultStore,
        output_dir: str | Path = "results",
        recent_rounds: int = 4,
        snapshot_interval: int = 10,
        max_state_tokens: int = 900,
        mode: str = "event_sourced_memory",
    ) -> None:
        self.system_prompt = system_prompt
        self.tool_registry = tool_registry
        self.result_store = result_store
        self.output_dir = Path(output_dir)
        self.recent_rounds = recent_rounds
        self.mode = mode
        self.enable_tool_externalization = True

        self.session_id = f"session_{uuid4().hex[:12]}"
        self.run_id = f"event_run_{int(time.time() * 1000)}_{uuid4().hex[:8]}"
        self.event_log = EventLog(self.output_dir / "event_log")
        self.projector = MemoryProjector()
        self.renderer = MemoryViewRenderer(max_state_tokens=max_state_tokens)
        self.snapshot_store = MemorySnapshotStore(self.output_dir / "event_memory_snapshots", interval=snapshot_interval)
        self.artifact_manager = ArtifactContextManager()
        self.state = TaskStateView()

        self.messages: list[dict] = []
        self.tool_results: list[ToolResult] = []
        self.loaded_skill_names: list[str] = []
        self.loaded_skill_tokens = 0
        self.last_token_breakdown: dict[str, int] = {}
        self.current_round = 0
        self.current_stage = "planning"
        self.current_query = ""
        self.last_prompt = ""
        self.memory_delta_count = 0

    def start_round(self, round_index: int, stage: str, user_input: str, run_id: str | None = None) -> None:
        self.current_round = int(round_index)
        self.current_stage = stage
        self.current_query = user_input

    def set_task_requirements(
        self,
        required_facts: list[str] | None = None,
        required_answer_points: list[str] | None = None,
    ) -> None:
        self.state.required_facts = _dedupe([*self.state.required_facts, *(required_facts or [])])
        self.state.required_answer_points = _dedupe(
            [*self.state.required_answer_points, *(required_answer_points or [])]
        )

    def record_tool_call(self, tool_name: str, user_input: str, stage: str) -> None:
        self._append_event(
            "tool_call",
            content=f"tool_name: {tool_name}\ninput: {_compact(user_input)}",
            source=tool_name,
            metadata={"tool_name": tool_name, "stage": stage},
        )

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self._append_event("user_message", content=content, source="user")

    def add_tool_result(self, result: ToolResult) -> None:
        self.tool_results.append(result)
        content = self._tool_prompt_record(result)
        self.messages.append(
            {
                "role": "tool",
                "content": content,
                "result_id": result.result_id,
                "tool_name": result.tool_name,
            }
        )
        self._append_event(
            "tool_result",
            content=result.summary,
            content_path=result.raw_path,
            token_count=result.summary_token_len,
            source=result.tool_name,
            metadata={
                "tool_name": result.tool_name,
                "result_id": result.result_id,
                "status": result.status,
                "summary": result.summary,
                "summary_token_len": result.summary_token_len,
                "raw_token_len": result.raw_token_len,
                "path": result.raw_path,
                "artifacts": result.artifacts,
            },
        )
        findings = _required_findings(result.summary, self.state.required_facts)
        if findings:
            self.state.tool_key_findings = _dedupe([*self.state.tool_key_findings, *findings])

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})
        event_type = "final_answer" if self.current_stage == "final_answer" else "reflection"
        self._append_event(event_type, content=content, source="assistant")

    def record_memory_delta(self, memory_delta: MemoryDelta) -> None:
        if memory_delta.is_empty():
            return
        self.memory_delta_count += 1
        self._append_event(
            "memory_delta",
            content=None,
            source="assistant",
            metadata={"memory_delta": memory_delta.to_dict()},
        )

    def build_extractor_payload(self, current_query: str, stage: str, assistant_response: str) -> dict:
        artifacts = [item.to_dict() for item in self.state.artifact_refs[-10:]]
        return {
            "schema": {
                "memory_delta": [
                    "goals",
                    "constraints",
                    "facts",
                    "decisions",
                    "open_questions",
                    "todos",
                    "artifact_refs",
                    "tool_summaries",
                    "warnings",
                ]
            },
            "stage": stage,
            "current_query": current_query,
            "recent_context": self._recent_turns(),
            "task_state": {
                "goals": list(self.state.goals[-8:]),
                "constraints": list(self.state.constraints[-10:]),
                "facts": [item.to_dict() for item in self.state.facts[-12:]],
                "decisions": [item.to_dict() for item in self.state.decisions[-10:]],
                "open_questions": list(self.state.open_questions[-8:]),
                "todos": list(self.state.todos[-10:]),
            },
            "tool_summaries": list(self.state.tool_summaries[-8:]),
            "required_facts": list(self.state.required_facts),
            "required_answer_points": list(self.state.required_answer_points),
            "tool_key_findings": list(self.state.tool_key_findings[-12:]),
            "artifact_refs": artifacts,
            "assistant_response": assistant_response,
            "instruction": "Return JSON only. Generate memory_delta for state update; do not answer the user.",
        }

    def record_metrics(self, metrics: dict) -> None:
        payload = {
            "input_tokens": metrics.get("prompt" + "_tokens", 0),
            "full_history_tokens": self._full_history_tokens(),
            "summary_tokens": metrics.get("summary_tokens", 0),
            "state_view_tokens": self.renderer.last_state_view_tokens,
            "latency": metrics.get("latency", 0),
            "ttft": metrics.get("ttft", -1),
            "success": metrics.get("success", False),
            "source": "runtime",
        }
        self._append_event("metric", content=json.dumps(payload, ensure_ascii=False), source="runtime", metadata=payload)

    def build_messages(self, stage: str = "planning", selected_tools: list[str] | None = None) -> list[dict[str, str]]:
        selected_tools = selected_tools or []
        self.current_stage = stage
        tool_briefs = json.dumps(self.tool_registry.list_tool_briefs(), ensure_ascii=False, indent=2)
        loaded_skills: list[str] = []
        for name in selected_tools:
            try:
                loaded_skills.append(f"## {name}\n{self.tool_registry.load_full_skill(name)}")
            except KeyError:
                continue
        loaded_skill_text = "\n\n".join(loaded_skills)
        self.loaded_skill_names = list(selected_tools)
        self.loaded_skill_tokens = estimate_tokens(loaded_skill_text)

        recent_turns = self._recent_turns()
        state_view = self.renderer.render(self.state, recent_turns, self.current_query, stage=stage)
        project_rules = (
            "固定说明：使用 Event-Sourced Memory，由 Event Log 投影出通用 Task State；"
            "工具结果只通过 result_id、summary 和 artifact metadata 引用；"
            "模型回答必须优先输出 JSON：assistant_response、next_action、memory_delta。"
        )
        prompt_parts = [
            f"[system]\n{self.system_prompt}",
            f"[project_rules]\n{project_rules}",
            f"[tool_briefs]\n{tool_briefs}",
            f"[loaded_skills]\n{loaded_skill_text}",
            f"[event_sourced_memory]\n{state_view}",
        ]
        prompt = "\n\n".join(prompt_parts)
        self.last_prompt = prompt
        self.last_token_breakdown = {
            "system": estimate_tokens(self.system_prompt) + estimate_tokens(project_rules),
            "tool_schema": estimate_tokens(tool_briefs) + estimate_tokens(loaded_skill_text),
            "history": estimate_tokens("\n".join(recent_turns)),
            "summary": 0,
            "tool_summary": 0,
            "branch": 0,
            "tool_brief": estimate_tokens(tool_briefs),
            "loaded_skill": estimate_tokens(loaded_skill_text),
            "state_view_tokens": self.renderer.last_state_view_tokens,
            "event_count": self.event_count,
            "memory_delta_count": self.memory_delta_count,
            "fact_count": len(self.state.facts),
            "decision_count": len(self.state.decisions),
            "artifact_ref_count": len(self.state.artifact_refs),
            "snapshot_count": self.snapshot_store.snapshot_count,
            "full_history_tokens": self._full_history_tokens(),
        }
        return [{"role": "user", "content": prompt}]

    def latest_metrics_hint(self) -> dict:
        raw_tool_tokens = sum(result.raw_token_len for result in self.tool_results)
        injected = sum(result.summary_token_len for result in self.tool_results)
        ratios = [result.compression_ratio for result in self.tool_results if result.raw_token_len > 0]
        return {
            **self.last_token_breakdown,
            "state_view_tokens": self.renderer.last_state_view_tokens,
            "event_count": self.event_count,
            "memory_delta_count": self.memory_delta_count,
            "fact_count": len(self.state.facts),
            "decision_count": len(self.state.decisions),
            "artifact_ref_count": len(self.state.artifact_refs),
            "snapshot_count": self.snapshot_store.snapshot_count,
            "full_history_tokens": self._full_history_tokens(),
            "raw_tool_tokens": raw_tool_tokens,
            "injected_tool_tokens": injected,
            "tool_compression_ratio": sum(ratios) / len(ratios) if ratios else 1.0,
            "loaded_skill_names": self.loaded_skill_names,
            "loaded_skill_tokens": self.loaded_skill_tokens,
            "memory_run_id": self.run_id,
        }

    def retention_text(self) -> str:
        facts = "\n".join(
            f"{item.content} (source={item.source}, confidence={item.confidence:.2f})" for item in self.state.facts[:40]
        )
        decisions = "\n".join(item.content for item in self.state.decisions[:15])
        artifacts = "\n".join(
            f"{ref.summary} {ref.result_id} {ref.tool_name} {ref.artifact_type} {ref.path}" for ref in self.state.artifact_refs[:20]
        )
        return "\n".join(
            [
                "\n".join(self.state.goals),
                "\n".join(self.state.constraints),
                facts,
                decisions,
                artifacts,
                self.last_prompt,
            ]
        )

    @property
    def event_count(self) -> int:
        return len(self.event_log.list_events(self.run_id))

    def _append_event(
        self,
        event_type: str,
        content: str | None = None,
        content_path: str | None = None,
        token_count: int | None = None,
        source: str = "agent",
        metadata: dict | None = None,
    ) -> AgentEvent:
        event = AgentEvent(
            event_id=f"evt_{uuid4().hex[:16]}",
            run_id=self.run_id,
            session_id=self.session_id,
            round=self.current_round,
            stage=self.current_stage,
            event_type=event_type,
            content=content,
            content_path=content_path,
            token_count=token_count if token_count is not None else estimate_tokens(content or ""),
            source=source,
            metadata=dict(metadata or {}),
        )
        event = self.event_log.append(event)
        self.state = self.projector.apply_event(self.state, event)
        for ref in self.state.artifact_refs:
            self.artifact_manager.register_artifact(ref)
        self.snapshot_store.maybe_save(self.run_id, self.state, self.event_count)
        return event

    def _tool_prompt_record(self, result: ToolResult) -> str:
        return "\n".join(
            [
                f"tool_name: {result.tool_name}",
                f"result_id: {result.result_id}",
                f"status: {result.status}",
                f"raw_token_len: {result.raw_token_len}",
                f"summary_token_len: {result.summary_token_len}",
                f"summary: {result.summary}",
                f"artifacts: {json.dumps(result.artifacts, ensure_ascii=False)}",
            ]
        )

    def _recent_turns(self) -> list[str]:
        count = max(1, self.recent_rounds) * 2
        recent = self.messages[-count:]
        return [f"{item.get('role', '')}: {_compact(str(item.get('content', '')), 260)}" for item in recent]

    def _full_history_tokens(self) -> int:
        return estimate_tokens("\n".join(f"{item.get('role', '')}: {item.get('content', '')}" for item in self.messages))


def _compact(text: str, max_chars: int = 240) -> str:
    single = " ".join(str(text).split())
    if len(single) <= max_chars:
        return single
    return single[:max_chars] + "..."


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _required_findings(summary: str, required_facts: list[str]) -> list[str]:
    findings: list[str] = []
    lowered = summary.lower()
    for fact in required_facts:
        if str(fact).lower() in lowered:
            findings.append(f"{fact}: covered by tool summary")
        else:
            findings.append(f"missing_required_fact: {fact}")
    return findings
