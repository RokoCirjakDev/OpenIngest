from __future__ import annotations

from OpenIngest.chunking.base import Chunker, ChunkingResult
from OpenIngest.chunking.task_splitter import build_child_chunks, detect_parent_sections
from OpenIngest.config import Settings
from OpenIngest.models import ChildChunk, ParentTaskSection, StructuredBlock


class ProcedureChunker(Chunker):
    def chunk(
        self,
        blocks: list[StructuredBlock],
        *,
        doc_id: str,
        metadata: dict[str, object],
        settings: Settings,
    ) -> ChunkingResult:
        parents = detect_parent_sections(blocks, doc_id, settings, metadata)
        chunks = build_child_chunks(parents, settings)
        return ChunkingResult(parents=parents, chunks=chunks)
