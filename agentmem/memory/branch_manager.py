from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from agentmem.memory.memory_object import estimate_tokens


@dataclass
class BranchNode:
    branch_id: str
    parent_id: str | None
    shared_context: str = ""
    deltas: list[str] = field(default_factory=list)


class BranchManager:
    """Agent 上下文层 Copy-on-Write 分支管理器。"""

    def __init__(self) -> None:
        self.branches: dict[str, BranchNode] = {}
        self.root_id: str | None = None

    def create_root(self, shared_context: str) -> str:
        branch_id = "root"
        self.branches[branch_id] = BranchNode(
            branch_id=branch_id,
            parent_id=None,
            shared_context=shared_context,
        )
        self.root_id = branch_id
        return branch_id

    def create_branch(self, parent_id: str, branch_id: str | None = None) -> str:
        if parent_id not in self.branches:
            raise KeyError(f"父分支不存在: {parent_id}")
        new_id = branch_id or f"branch_{uuid4().hex[:8]}"
        self.branches[new_id] = BranchNode(branch_id=new_id, parent_id=parent_id)
        return new_id

    def add_delta(self, branch_id: str, content: str) -> None:
        if branch_id not in self.branches:
            raise KeyError(f"分支不存在: {branch_id}")
        self.branches[branch_id].deltas.append(content)

    def build_context(self, branch_id: str) -> str:
        if branch_id not in self.branches:
            raise KeyError(f"分支不存在: {branch_id}")
        chain: list[BranchNode] = []
        cursor: str | None = branch_id
        while cursor is not None:
            node = self.branches[cursor]
            chain.append(node)
            cursor = node.parent_id
        chain.reverse()

        parts: list[str] = []
        for node in chain:
            if node.shared_context:
                parts.append(node.shared_context)
            parts.extend(node.deltas)
        return "\n".join(parts)

    def calculate_sharing_ratio(self) -> float:
        if not self.root_id or self.root_id not in self.branches:
            return 0.0
        root_tokens = estimate_tokens(self.branches[self.root_id].shared_context)
        branch_count = max(1, len(self.branches) - 1)
        naive_tokens = root_tokens * branch_count
        actual_tokens = root_tokens
        for branch_id, node in self.branches.items():
            if branch_id == self.root_id:
                continue
            actual_tokens += sum(estimate_tokens(delta) for delta in node.deltas)
        if naive_tokens == 0:
            return 0.0
        return max(0.0, 1.0 - actual_tokens / naive_tokens)

