from __future__ import annotations

from pathlib import Path

from agentmem.event_memory.memory_delta import ArtifactRef
from agentmem.memory.memory_object import estimate_tokens


class ArtifactContextManager:
    """Bounded artifact lookup by caller-provided terms."""

    def __init__(self) -> None:
        self.refs: dict[str, ArtifactRef] = {}
        self.context_load_count = 0
        self.context_tokens = 0

    def register_artifact(self, artifact_ref: ArtifactRef) -> None:
        key = artifact_ref.result_id or artifact_ref.path
        if key:
            self.refs[key] = artifact_ref

    def search_artifacts(self, terms: list[str], top_k: int = 3) -> list[ArtifactRef]:
        normalized = [term.lower() for term in terms if str(term).strip()]
        if not normalized:
            return []
        matches: list[tuple[int, ArtifactRef]] = []
        for ref in self.refs.values():
            haystack = " ".join([ref.summary, ref.path, ref.result_id, ref.tool_name, ref.artifact_type]).lower()
            score = sum(1 for term in normalized if term in haystack)
            if score > 0:
                matches.append((score, ref))
        matches.sort(key=lambda item: (item[0], item[1].token_count), reverse=True)
        return [ref for _, ref in matches[:top_k]]

    def load_artifact_context(self, artifact_id: str, max_tokens: int = 256, terms: list[str] | None = None) -> str:
        ref = self.refs.get(artifact_id)
        if ref is None:
            return ""
        max_chars = max(128, max_tokens * 4)
        path = Path(ref.path) if ref.path else None
        if not path or not path.exists():
            return ref.summary[:max_chars]
        text = path.read_text(encoding="utf-8", errors="replace")
        snippet = _term_snippet(text, terms or [], max_chars=max_chars)
        return snippet or text[:max_chars]

    def create_artifact_context(self, terms: list[str], max_tokens_per_ref: int = 180) -> str:
        refs = self.search_artifacts(terms, top_k=3)
        parts: list[str] = []
        for ref in refs:
            artifact_id = ref.result_id or ref.path
            snippet = self.load_artifact_context(artifact_id, max_tokens=max_tokens_per_ref, terms=terms)
            if not snippet:
                continue
            parts.append(
                "\n".join(
                    [
                        f"result_id: {ref.result_id}",
                        f"tool_name: {ref.tool_name}",
                        f"type: {ref.artifact_type}",
                        f"path: {ref.path}",
                        f"summary: {ref.summary}",
                        f"snippet: {snippet}",
                    ]
                )
            )
        context = "\n\n".join(parts)
        if context:
            self.context_load_count += 1
            self.context_tokens += estimate_tokens(context)
        return context


def _term_snippet(text: str, terms: list[str], max_chars: int) -> str:
    lowered = text.lower()
    for term in terms:
        index = lowered.find(term.lower())
        if index < 0:
            continue
        start = max(0, index - max_chars // 3)
        return text[start : start + max_chars]
    return ""
