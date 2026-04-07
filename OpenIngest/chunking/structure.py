from __future__ import annotations

from uuid import uuid4

from OpenIngest.chunking.base import Chunker, ChunkingResult
from OpenIngest.chunking.task_splitter import build_child_chunks
from OpenIngest.config import Settings
from OpenIngest.models import ChildChunk, ParentTaskSection, StructuredBlock


class StructureChunker(Chunker):
    def chunk(
        self,
        blocks: list[StructuredBlock],
        *,
        doc_id: str,
        metadata: dict[str, object],
        settings: Settings,
    ) -> ChunkingResult:
        parents: list[ParentTaskSection] = []
        current_blocks: list[StructuredBlock] = []
        current_title = "Document"
        current_breadcrumbs: list[str] = []

        def flush() -> None:
            nonlocal current_blocks, current_title, current_breadcrumbs
            if not current_blocks:
                return
            page_from_values = [block.page_from for block in current_blocks if block.page_from is not None]
            page_to_values = [block.page_to for block in current_blocks if block.page_to is not None]
            text = "\n".join(block.text for block in current_blocks if block.text.strip())
            parents.append(
                ParentTaskSection(
                    section_id=str(uuid4()),
                    doc_id=doc_id,
                    title=current_title,
                    breadcrumbs=list(current_breadcrumbs),
                    page_from=min(page_from_values) if page_from_values else None,
                    page_to=max(page_to_values) if page_to_values else None,
                    parent_text=text,
                    metadata=dict(metadata),
                )
            )
            current_blocks = []

        for block in blocks:
            if block.type == "heading":
                if current_blocks:
                    flush()
                current_title = block.text
                current_breadcrumbs = [part for part in (block.breadcrumbs or "").split(" > ") if part]
                continue
            current_blocks.append(block)

        flush()
        chunks = build_child_chunks(parents, settings)
        return ChunkingResult(parents=parents, chunks=chunks)
