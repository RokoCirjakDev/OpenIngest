from __future__ import annotations

from uuid import uuid4

from OpenIngest.chunking.base import Chunker, ChunkingResult
from OpenIngest.config import Settings
from OpenIngest.models import ChildChunk, ParentTaskSection, StructuredBlock
from OpenIngest.utils import estimate_tokens


class SlidingWindowChunker(Chunker):
    def _window(self, lines: list[str], settings: Settings) -> list[list[str]]:
        chunks: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0
        overlap = max(0, settings.chunking.overlap_steps)

        for line in lines:
            line_tokens = estimate_tokens(line)
            if current and current_tokens + line_tokens > settings.chunking.hard_cap_tokens:
                chunks.append(current)
                current = current[-overlap:] if overlap else []
                current_tokens = sum(estimate_tokens(item) for item in current)
            current.append(line)
            current_tokens += line_tokens
            if current_tokens >= settings.chunking.target_tokens:
                chunks.append(current)
                current = current[-overlap:] if overlap else []
                current_tokens = sum(estimate_tokens(item) for item in current)

        if current:
            chunks.append(current)
        return chunks

    def chunk(
        self,
        blocks: list[StructuredBlock],
        *,
        doc_id: str,
        metadata: dict[str, object],
        settings: Settings,
    ) -> ChunkingResult:
        text_lines = [block.text.strip() for block in blocks if block.text.strip()]
        parent = ParentTaskSection(
            section_id=str(uuid4()),
            doc_id=doc_id,
            title=str(metadata.get("title") or "Document"),
            breadcrumbs=[],
            parent_text="\n".join(text_lines),
            metadata=dict(metadata),
        )
        chunks: list[ChildChunk] = []
        for group in self._window(text_lines, settings):
            chunk_text = "\n".join(group)
            chunks.append(
                ChildChunk(
                    chunk_id=str(uuid4()),
                    section_id=parent.section_id,
                    doc_id=doc_id,
                    chunk_type="task",
                    chunk_text=chunk_text,
                    breadcrumbs=[],
                    metadata=dict(metadata),
                )
            )
        return ChunkingResult(parents=[parent], chunks=chunks)
