from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolResult:
    result_id: str
    tool_name: str
    status: str
    raw_result: str
    summary: str
    raw_token_len: int
    summary_token_len: int
    raw_path: str | None
    chunks: list[dict[str, Any]]
    latency: float
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_raw: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_raw:
            data["raw_result"] = ""
        return data

    @property
    def compression_ratio(self) -> float:
        if self.raw_token_len <= 0:
            return 1.0
        return self.summary_token_len / self.raw_token_len

