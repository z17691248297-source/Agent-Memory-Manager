from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .schema import AgentMeta


@dataclass
class CacheAccounting:
    by_segment: Counter[str] = field(default_factory=Counter)
    by_namespace: Counter[str] = field(default_factory=Counter)

    def observe(self, meta: AgentMeta | None, blocks: int) -> None:
        if meta is None:
            return
        self.by_segment[meta.segment_type] += int(blocks)
        self.by_namespace[meta.cache_namespace or meta.session_id] += int(blocks)
