from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MemoryType(str, Enum):
    SYSTEM = "system"
    TOOL_SCHEMA = "tool_schema"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_RESULT = "tool_result"
    SUMMARY = "summary"
    BRANCH_DELTA = "branch_delta"


class Placement(str, Enum):
    STABLE_PREFIX = "stable_prefix"
    DYNAMIC_CONTEXT = "dynamic_context"
    ARTIFACT_REF = "artifact_ref"
    DROPPED = "dropped"


@dataclass(frozen=True)
class MemoryObject:
    """上下文编译器可分析、可打分、可取舍的记忆单元。"""

    memory_id: str
    memory_type: MemoryType
    content: str
    summary: str = ""
    source: str = ""
    importance: float = 0.5
    recency: float = 0.5
    prefix_stable: bool = False
    branch_id: str | None = None

    @property
    def token_count(self) -> int:
        return estimate_tokens(self.content)

    @property
    def summary_token_count(self) -> int:
        return estimate_tokens(self.summary)


def estimate_tokens(text: str) -> int:
    """
    轻量 token 估算函数，用于本地可复现实验。

    这里故意不依赖具体模型 tokenizer，避免第一版 benchmark 被模型环境卡住。
    它适合比较不同策略的相对 token 变化；后续接入 vLLM 后，可以替换成
    本地模型实际 tokenizer 的精确计数。
    """
    clean = text.strip()
    if not clean:
        return 0
    return max(1, (len(clean) + 3) // 4)
