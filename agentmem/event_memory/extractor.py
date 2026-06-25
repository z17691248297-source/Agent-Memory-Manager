from __future__ import annotations

from dataclasses import dataclass

from agentmem.event_memory.event import AgentEvent
from agentmem.event_memory.memory_delta import MemoryDelta


@dataclass
class ExtractedFacts:
    """Compatibility wrapper for older imports.

    Event-sourced memory no longer extracts domain facts from natural language.
    Structured memory updates enter through explicit MemoryDelta events.
    """

    memory_delta: MemoryDelta


class StructuredExtractor:
    """No-op extractor kept for compatibility.

    The core memory layer must not encode benchmark-specific vocabulary or
    parse tool output into task facts. Tools produce artifact summaries, and
    the agent writes durable state through memory_delta.
    """

    def extract(self, event: AgentEvent) -> ExtractedFacts:
        return ExtractedFacts(memory_delta=MemoryDelta())
