from __future__ import annotations

import json
from hashlib import sha256
from dataclasses import asdict, dataclass
from pathlib import Path

from agent.memory_object import estimate_tokens


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    source_memory_id: str
    summary: str
    full_token_count: int
    page_count: int
    path: str


class ArtifactStore:
    """把长工具结果外置保存，并在 prompt 中只暴露短引用。"""

    def __init__(self, root_dir: str | Path = "benchmarks/results/artifacts") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        source_memory_id: str,
        content: str,
        summary: str,
        page_chars: int = 1600,
    ) -> ArtifactRecord:
        content_hash = sha256(content.encode("utf-8")).hexdigest()[:16]
        artifact_id = f"{source_memory_id}-{content_hash}"
        full_path = self.root_dir / f"{artifact_id}.txt"
        meta_path = self.root_dir / f"{artifact_id}.json"

        full_path.write_text(content, encoding="utf-8")
        page_count = max(1, (len(content) + page_chars - 1) // page_chars)
        record = ArtifactRecord(
            artifact_id=artifact_id,
            source_memory_id=source_memory_id,
            summary=summary,
            full_token_count=estimate_tokens(content),
            page_count=page_count,
            path=str(full_path),
        )
        meta_path.write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record

    def read_page(self, artifact_id: str, page: int = 1, page_chars: int = 1600) -> str:
        if page <= 0:
            raise ValueError("page must be positive")

        full_path = self.root_dir / f"{artifact_id}.txt"
        if not full_path.exists():
            raise FileNotFoundError(f"artifact not found: {artifact_id}")

        content = full_path.read_text(encoding="utf-8")
        start = (page - 1) * page_chars
        end = start + page_chars
        return content[start:end]
