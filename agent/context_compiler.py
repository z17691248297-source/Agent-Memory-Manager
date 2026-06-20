from __future__ import annotations

from dataclasses import asdict, dataclass

from agent.artifact_store import ArtifactRecord, ArtifactStore
from agent.memory_object import MemoryObject, MemoryType, Placement, estimate_tokens
from agent.policies import ContextPolicy


@dataclass(frozen=True)
class CompiledItem:
    memory_id: str
    memory_type: str
    placement: str
    token_count: int
    original_token_count: int
    content: str
    artifact_id: str | None = None


@dataclass(frozen=True)
class CompileTrace:
    policy_name: str
    token_budget: int
    total_input_tokens: int
    stable_prefix_tokens: int
    dynamic_context_tokens: int
    inline_tool_result_tokens: int
    artifact_ref_tokens: int
    artifact_saved_tokens: int
    dropped_tokens: int
    item_count: int
    artifact_count: int
    compiled_items: list[dict]


@dataclass(frozen=True)
class CompiledContext:
    prompt: str
    trace: CompileTrace


class ContextCompiler:
    def __init__(self, artifact_store: ArtifactStore | None = None) -> None:
        self.artifact_store = artifact_store or ArtifactStore()

    def compile(
        self,
        memory_objects: list[MemoryObject],
        policy: ContextPolicy,
        active_branch_id: str | None = None,
    ) -> CompiledContext:
        selected: list[CompiledItem] = []
        artifacts: list[ArtifactRecord] = []
        dropped_tokens = 0

        # 稳定前缀区：system prompt、工具 schema 等高复用内容。
        # 这部分越稳定，后续越容易和 vLLM prefix caching 对齐。
        stable_prefix_objects = self._stable_prefix(memory_objects, policy)

        # 动态上下文区：历史消息、摘要、工具结果、分支增量等。
        # 不同 policy 会决定保留多少、是否外置、是否按重要性选择。
        dynamic_objects = self._dynamic_objects(memory_objects, policy, active_branch_id)

        current_tokens = 0
        for memory in stable_prefix_objects:
            item = self._inline_item(memory, Placement.STABLE_PREFIX)
            selected.append(item)
            current_tokens += item.token_count

        for memory in dynamic_objects:
            item, artifact = self._compile_dynamic_memory(memory, policy)

            if artifact is not None:
                artifacts.append(artifact)

            if current_tokens + item.token_count <= policy.token_budget:
                selected.append(item)
                current_tokens += item.token_count
            else:
                dropped_tokens += memory.token_count
                selected.append(self._dropped_item(memory))

        prompt = self._render_prompt(selected, policy)
        trace = self._build_trace(
            policy=policy,
            selected=selected,
            artifacts=artifacts,
            dropped_tokens=dropped_tokens,
        )
        return CompiledContext(prompt=prompt, trace=trace)

    def _stable_prefix(
        self,
        memory_objects: list[MemoryObject],
        policy: ContextPolicy,
    ) -> list[MemoryObject]:
        if not policy.stable_prefix:
            return []
        return [
            memory
            for memory in memory_objects
            if memory.prefix_stable
            or memory.memory_type in {MemoryType.SYSTEM, MemoryType.TOOL_SCHEMA}
        ]

    def _dynamic_objects(
        self,
        memory_objects: list[MemoryObject],
        policy: ContextPolicy,
        active_branch_id: str | None,
    ) -> list[MemoryObject]:
        stable_ids = {
            memory.memory_id for memory in self._stable_prefix(memory_objects, policy)
        }
        dynamic = [
            memory for memory in memory_objects if memory.memory_id not in stable_ids
        ]

        if active_branch_id is not None:
            dynamic = [
                memory
                for memory in dynamic
                if memory.branch_id is None or memory.branch_id == active_branch_id
            ]

        if not policy.use_summary:
            dynamic = [memory for memory in dynamic if memory.memory_type != MemoryType.SUMMARY]

        messages = [
            memory
            for memory in dynamic
            if memory.memory_type
            in {
                MemoryType.USER_MESSAGE,
                MemoryType.ASSISTANT_MESSAGE,
                MemoryType.TOOL_RESULT,
                MemoryType.BRANCH_DELTA,
            }
        ]
        summaries = [memory for memory in dynamic if memory.memory_type == MemoryType.SUMMARY]

        if policy.name == "baseline":
            return dynamic

        recent_messages = messages[-policy.recent_message_limit :]
        result = summaries + recent_messages

        if policy.use_importance_selection:
            older_candidates = messages[: -policy.recent_message_limit]
            ranked = sorted(
                older_candidates,
                key=lambda memory: self._utility_score(memory),
                reverse=True,
            )
            result = summaries + ranked[:4] + recent_messages

        return self._dedupe_preserve_order(result)

    def _compile_dynamic_memory(
        self,
        memory: MemoryObject,
        policy: ContextPolicy,
    ) -> tuple[CompiledItem, ArtifactRecord | None]:
        if memory.memory_type != MemoryType.TOOL_RESULT:
            return self._inline_item(memory, Placement.DYNAMIC_CONTEXT), None

        if policy.inline_tool_results or memory.token_count <= policy.tool_result_inline_token_limit:
            return self._inline_item(memory, Placement.DYNAMIC_CONTEXT), None

        if not policy.externalize_tool_results:
            return self._dropped_item(memory), None

        # 长工具结果不直接塞进 prompt，而是保存到 artifact store。
        # prompt 中只放 artifact_id、摘要、页数和原始 token 数。
        summary = memory.summary or self._fallback_summary(memory.content)
        artifact = self.artifact_store.save(memory.memory_id, memory.content, summary)
        ref_content = (
            "[工具结果已外置保存]\n"
            f"artifact_id: {artifact.artifact_id}\n"
            f"来源记忆: {memory.memory_id}\n"
            f"摘要: {summary}\n"
            f"原始 token 数: {artifact.full_token_count}\n"
            f"页数: {artifact.page_count}\n"
            "如果需要精确细节，请调用 read_artifact_page。"
        )
        item = CompiledItem(
            memory_id=memory.memory_id,
            memory_type=memory.memory_type.value,
            placement=Placement.ARTIFACT_REF.value,
            token_count=estimate_tokens(ref_content),
            original_token_count=memory.token_count,
            content=ref_content,
            artifact_id=artifact.artifact_id,
        )
        return item, artifact

    def _inline_item(self, memory: MemoryObject, placement: Placement) -> CompiledItem:
        return CompiledItem(
            memory_id=memory.memory_id,
            memory_type=memory.memory_type.value,
            placement=placement.value,
            token_count=memory.token_count,
            original_token_count=memory.token_count,
            content=memory.content,
        )

    def _dropped_item(self, memory: MemoryObject) -> CompiledItem:
        return CompiledItem(
            memory_id=memory.memory_id,
            memory_type=memory.memory_type.value,
            placement=Placement.DROPPED.value,
            token_count=0,
            original_token_count=memory.token_count,
            content="",
        )

    def _render_prompt(self, selected: list[CompiledItem], policy: ContextPolicy) -> str:
        sections: list[str] = [f"[上下文策略: {policy.name}]"]
        for item in selected:
            if item.placement == Placement.DROPPED.value:
                continue
            sections.append(
                "\n".join(
                    [
                        f"[{item.placement}:{item.memory_type}:{item.memory_id}]",
                        item.content,
                    ]
                )
            )
        return "\n\n".join(sections)

    def _build_trace(
        self,
        policy: ContextPolicy,
        selected: list[CompiledItem],
        artifacts: list[ArtifactRecord],
        dropped_tokens: int,
    ) -> CompileTrace:
        stable_prefix_tokens = sum(
            item.token_count
            for item in selected
            if item.placement == Placement.STABLE_PREFIX.value
        )
        artifact_ref_tokens = sum(
            item.token_count
            for item in selected
            if item.placement == Placement.ARTIFACT_REF.value
        )
        dynamic_tokens = sum(
            item.token_count
            for item in selected
            if item.placement == Placement.DYNAMIC_CONTEXT.value
        )
        inline_tool_tokens = sum(
            item.token_count
            for item in selected
            if item.memory_type == MemoryType.TOOL_RESULT.value
            and item.placement == Placement.DYNAMIC_CONTEXT.value
        )
        artifact_saved_tokens = sum(
            max(0, item.original_token_count - item.token_count)
            for item in selected
            if item.placement == Placement.ARTIFACT_REF.value
        )
        total_input_tokens = stable_prefix_tokens + dynamic_tokens + artifact_ref_tokens

        return CompileTrace(
            policy_name=policy.name,
            token_budget=policy.token_budget,
            total_input_tokens=total_input_tokens,
            stable_prefix_tokens=stable_prefix_tokens,
            dynamic_context_tokens=dynamic_tokens,
            inline_tool_result_tokens=inline_tool_tokens,
            artifact_ref_tokens=artifact_ref_tokens,
            artifact_saved_tokens=artifact_saved_tokens,
            dropped_tokens=dropped_tokens,
            item_count=len([item for item in selected if item.placement != Placement.DROPPED.value]),
            artifact_count=len(artifacts),
            compiled_items=[asdict(item) for item in selected],
        )

    def _utility_score(self, memory: MemoryObject) -> float:
        return (0.65 * memory.importance + 0.35 * memory.recency) / max(
            memory.token_count,
            1,
        )

    def _fallback_summary(self, content: str, max_chars: int = 320) -> str:
        clean = " ".join(content.split())
        if len(clean) <= max_chars:
            return clean
        return clean[:max_chars] + "..."

    def _dedupe_preserve_order(self, memories: list[MemoryObject]) -> list[MemoryObject]:
        seen: set[str] = set()
        result: list[MemoryObject] = []
        for memory in memories:
            if memory.memory_id in seen:
                continue
            seen.add(memory.memory_id)
            result.append(memory)
        return result
