from __future__ import annotations

from dataclasses import dataclass

from agent.memory_object import MemoryObject, MemoryType


@dataclass(frozen=True)
class Scenario:
    """一个可复现的 Agent 记忆压力场景。"""

    scenario_id: str
    description: str
    memory_objects: list[MemoryObject]
    active_branch_id: str | None = None


def build_all_scenarios() -> list[Scenario]:
    return [
        build_long_tool_result_scenario(),
        build_multi_turn_summary_scenario(),
        build_branch_planning_scenario(),
    ]


def stable_system_prompt() -> MemoryObject:
    return MemoryObject(
        memory_id="stable_system",
        memory_type=MemoryType.SYSTEM,
        content=(
            "你是一个用于 vLLM serving benchmark 的实验型 Agent。"
            "请遵守 JSON action 协议，回答必须基于已提供的 memory objects。"
            "只有在需要精确证据时，才请求读取 artifact page。"
        ),
        importance=1.0,
        recency=1.0,
        prefix_stable=True,
    )


def stable_tool_schema() -> MemoryObject:
    return MemoryObject(
        memory_id="stable_tool_schema",
        memory_type=MemoryType.TOOL_SCHEMA,
        content=(
            "可用工具，顺序固定：\n"
            "1. search_docs(query: string, top_k: number) -> 文本片段\n"
            "2. read_artifact_page(artifact_id: string, page: number) -> 文本\n"
            "3. save_note(note: string) -> 保存确认\n"
            "4. final_answer(answer: string) -> 最终回答\n"
            "工具输出可能会被外置保存。除非确实需要原始细节，否则优先使用 artifact 引用和摘要。"
        ),
        importance=1.0,
        recency=1.0,
        prefix_stable=True,
    )


def build_long_tool_result_scenario() -> Scenario:
    """长工具结果场景：验证外置 artifact 是否能减少 prompt token。"""

    objects = [stable_system_prompt(), stable_tool_schema()]
    objects.extend(
        [
            MemoryObject(
                memory_id="u_001",
                memory_type=MemoryType.USER_MESSAGE,
                content="比较普通聊天和 Agent 工具调用流程中的 KV Cache 压力。",
                importance=0.8,
                recency=0.4,
            ),
            MemoryObject(
                memory_id="a_001",
                memory_type=MemoryType.ASSISTANT_MESSAGE,
                content="我会先查看笔记并搜索 benchmark 文档，再给出对比结论。",
                importance=0.5,
                recency=0.4,
            ),
            MemoryObject(
                memory_id="tool_search_001",
                memory_type=MemoryType.TOOL_RESULT,
                content=_repeat_paragraph(
                    "文档片段：Agent 工作流会反复携带 system prompt、工具 schema、"
                    "observation、日志、检索片段和中间计划。如果把原始工具结果直接放进 "
                    "prompt，prefill token 会增加，额外 KV cache block 也会在 decode "
                    "阶段继续占用。",
                    repeat=55,
                ),
                summary=(
                    "检索结果表明，原始工具 observation 会增加 prefill token，并让额外 "
                    "KV cache block 在 decode 阶段继续存活。"
                ),
                source="search_docs",
                importance=0.9,
                recency=0.6,
            ),
            MemoryObject(
                memory_id="u_002",
                memory_type=MemoryType.USER_MESSAGE,
                content=(
                    "现在写出最终对比，并说明为什么工具结果外置能帮助 vLLM。"
                ),
                importance=1.0,
                recency=1.0,
            ),
        ]
    )
    return Scenario(
        scenario_id="long_tool_result",
        description="长检索结果应该被编译成 artifact 引用。",
        memory_objects=objects,
    )


def build_multi_turn_summary_scenario() -> Scenario:
    """多轮历史场景：验证旧历史是否能被摘要和最近窗口替代。"""

    objects = [stable_system_prompt(), stable_tool_schema()]
    for index in range(1, 15):
        recency = index / 14
        objects.append(
            MemoryObject(
                memory_id=f"u_hist_{index:02d}",
                memory_type=MemoryType.USER_MESSAGE,
                content=(
                    f"第 {index} 轮：请记住 benchmark 约束 C{index}："
                    "保持 prefix 稳定，并避免不必要的原始工具文本。"
                ),
                importance=0.35 + (0.02 * index),
                recency=recency,
            )
        )
        objects.append(
            MemoryObject(
                memory_id=f"a_hist_{index:02d}",
                memory_type=MemoryType.ASSISTANT_MESSAGE,
                content=(
                    f"第 {index} 轮：已记录约束 C{index}。如果它变成旧上下文，"
                    "我会通过 summary memory 保留关键内容。"
                ),
                importance=0.25 + (0.01 * index),
                recency=recency,
            )
        )

    objects.append(
        MemoryObject(
            memory_id="summary_001",
            memory_type=MemoryType.SUMMARY,
            content=(
                "较早对话已经确定：benchmark 必须保持稳定 prefix，避免原始长工具输出，"
                "记录 token 节省量，并比较 baseline 与优化后的上下文策略。"
            ),
            importance=0.95,
            recency=0.9,
        )
    )
    objects.append(
        MemoryObject(
            memory_id="u_final",
            memory_type=MemoryType.USER_MESSAGE,
            content="结合所有历史约束，输出最终 benchmark 计划。",
            importance=1.0,
            recency=1.0,
        )
    )
    return Scenario(
        scenario_id="multi_turn_summary",
        description="旧对话应该被 summary 和最近窗口压缩。",
        memory_objects=objects,
    )


def build_branch_planning_scenario() -> Scenario:
    """分支规划场景：验证只保留活跃分支是否能减少重复上下文。"""

    objects = [stable_system_prompt(), stable_tool_schema()]
    objects.extend(
        [
            MemoryObject(
                memory_id="root_goal",
                memory_type=MemoryType.USER_MESSAGE,
                content=(
                    "我们需要为 Agent 记忆系统选择一个设计：简单最近窗口 baseline、"
                    "artifact memory，或者 branch-aware compiler。"
                ),
                importance=1.0,
                recency=0.7,
            ),
            MemoryObject(
                memory_id="branch_A",
                memory_type=MemoryType.BRANCH_DELTA,
                branch_id="A",
                content=(
                    "分支 A 探索简单最近窗口设计。它实现容易，但会丢失较早约束，"
                    "也没有优化工具结果记忆。"
                ),
                importance=0.45,
                recency=0.6,
            ),
            MemoryObject(
                memory_id="branch_B",
                memory_type=MemoryType.BRANCH_DELTA,
                branch_id="B",
                content=(
                    "分支 B 探索 artifact memory。它把原始 observation 放在 prompt 外部，"
                    "只在上下文里保留摘要，并在需要精确细节时按页读取。"
                ),
                importance=0.9,
                recency=0.8,
            ),
            MemoryObject(
                memory_id="branch_C",
                memory_type=MemoryType.BRANCH_DELTA,
                branch_id="C",
                content=(
                    "分支 C 探索直接修改 vLLM scheduler。这个方向可能更强，"
                    "但需要更深的引擎改动，风险也更高。"
                ),
                importance=0.7,
                recency=0.5,
            ),
            MemoryObject(
                memory_id="branch_B_tool",
                memory_type=MemoryType.TOOL_RESULT,
                branch_id="B",
                content=_repeat_paragraph(
                    "分支 B 证据：artifact 引用能保留任务相关摘要，同时把原始日志移出 "
                    "prompt。这会让输入长度更可控，也让 prompt 结构更适合 vLLM "
                    "prefix cache 复用。",
                    repeat=35,
                ),
                summary=(
                    "Artifact memory 能让 prompt 更可控，并避免原始日志导致上下文膨胀。"
                ),
                importance=0.95,
                recency=0.9,
            ),
            MemoryObject(
                memory_id="u_branch_final",
                memory_type=MemoryType.USER_MESSAGE,
                content="选择分支 B，并说明为什么它适合作为初学者友好的比赛方案。",
                importance=1.0,
                recency=1.0,
            ),
        ]
    )
    return Scenario(
        scenario_id="branch_planning",
        description="只应编译活跃分支和公共根上下文。",
        memory_objects=objects,
        active_branch_id="B",
    )


def _repeat_paragraph(paragraph: str, repeat: int) -> str:
    return "\n".join(f"{idx + 1}. {paragraph}" for idx in range(repeat))
