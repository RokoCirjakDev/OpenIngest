from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from OpenIngest.config import Settings
from OpenIngest.models import ChildChunk, ParentTaskSection, StructuredBlock


@dataclass(slots=True)
class ChunkingResult:
    parents: list[ParentTaskSection]
    chunks: list[ChildChunk]


class Chunker(ABC):
    @abstractmethod
    def chunk(
        self,
        blocks: list[StructuredBlock],
        *,
        doc_id: str,
        metadata: dict[str, object],
        settings: Settings,
    ) -> ChunkingResult:
        raise NotImplementedError
