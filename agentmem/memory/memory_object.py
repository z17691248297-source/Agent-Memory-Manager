from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any


class MemoryType(str, Enum):
    PROJECT = "project_memory"
    SESSION = "session_memory"
    TOOL = "tool_memory"
    BRANCH = "branch_memory"
    RUNTIME = "runtime_memory"


class Lifecycle(str, Enum):
    STATIC = "static"
    SESSION = "session"
    TURN = "turn"
    BRANCH = "branch"
    ARTIFACT = "artifact"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_tokens(text: str) -> int:
    """轻量 token 估算，MVP 默认不依赖具体模型 tokenizer。"""
    clean = text.strip()
    if not clean:
        return 0
    return max(1, (len(clean) + 3) // 4)


def hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass
class MemoryObject:
    """Agent 上下文中的一个分层内存对象。"""

    id: str
    type: MemoryType
    content: str
    priority: float = 0.5
    lifecycle: Lifecycle = Lifecycle.SESSION
    token_count: int | None = None
    hash_value: str | None = None
    created_at: str = field(default_factory=utc_now)
    last_access_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.token_count is None:
            self.token_count = estimate_tokens(self.content)
        if self.hash_value is None:
            self.hash_value = hash_text(self.content)

    def touch(self) -> None:
        self.last_access_at = utc_now()

