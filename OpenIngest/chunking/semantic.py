from __future__ import annotations

from OpenIngest.chunking.base import Chunker, ChunkingResult
from OpenIngest.chunking.structure import StructureChunker
from OpenIngest.config import Settings
from OpenIngest.models import ChildChunk, ParentTaskSection, StructuredBlock


class SemanticChunker(Chunker):
    def chunk(
        self,
        blocks: list[StructuredBlock],
        *,
        doc_id: str,
        metadata: dict[str, object],
        settings: Settings,
    ) -> ChunkingResult:
        # Placeholder semantic chunker: keeps the API pluggable and falls back to structure-based splits.
        return StructureChunker().chunk(blocks, doc_id=doc_id, metadata=metadata, settings=settings)
