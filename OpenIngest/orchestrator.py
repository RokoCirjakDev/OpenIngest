from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from OpenIngest.chunking import compute_breadcrumbs, get_chunker, merge_image_descriptions
from OpenIngest.config import PipelineConfig, load_config
from OpenIngest.embed import embed_child_chunks
from OpenIngest.enrich import enrich_images_with_vision, enrich_parent_sections
from OpenIngest.extractors import extract_docx, extract_pdf
from OpenIngest.models import (
    ChildChunk,
    ChunkRecord,
    ChunkRecordEmbedding,
    ChunkRecordSource,
    ChunkRecordText,
    ChunkRecordUnit,
    ExtractionResult,
    IngestStats,
    ParentTaskSection,
    PipelineState,
    SourceDocument,
)
from OpenIngest.utils import JsonStateStore, configure_logging, sha256_file
from OpenIngest.writers import JsonlWriter, Oracle23aiWriter, WriteResult, Writer


logger = logging.getLogger("openingest.orchestrator")


class PipelineRunner:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def _build_writer(self) -> Writer:
        kind = (self.config.writer.kind or "oracle23ai").lower()
        if kind == "jsonl":
            output_path = self.config.writer.mapping.get("output_path", "ingest-debug.jsonl")
            return JsonlWriter(str(output_path))
        if kind in {"oracle", "oracle23ai"}:
            return Oracle23aiWriter(self.config)
        raise ValueError(f"Unsupported writer kind: {self.config.writer.kind}")

    def _source_type(self, file_path: str) -> str:
        return Path(file_path).suffix.lower().lstrip(".") or "unknown"

    def _choose_extractor(self, file_path: str, metadata: dict[str, object]) -> ExtractionResult:
        file_ext = Path(file_path).suffix.lower()
        if file_ext == ".docx":
            return extract_docx(file_path, metadata)
        if file_ext == ".pdf":
            return extract_pdf(file_path, metadata, self.config)
        raise ValueError(f"Unsupported file type: {file_ext}")

    def _to_state(self, extraction: ExtractionResult) -> PipelineState:
        source = SourceDocument(
            doc_id=extraction.document.doc_id,
            source_uri=extraction.document.source_uri,
            source_type=self._source_type(extraction.document.source_uri),
            title=extraction.document.title,
            metadata=dict(extraction.document.metadata),
        )
        return PipelineState(source=source, blocks=list(extraction.document.blocks), images=list(extraction.images))

    def _nearest_heading_map(self, extraction: ExtractionResult) -> dict[str, str]:
        heading = ""
        out: dict[str, str] = {}
        image_lookup = {image.image_id: image for image in extraction.images}
        for block in extraction.document.blocks:
            if block.type == "heading":
                heading = block.text
                continue
            if block.type == "image_anchor" and block.anchor_image_id in image_lookup:
                out[block.anchor_image_id] = heading
        return out

    def _to_records(
        self,
        chunks: list[ChildChunk],
        parents: list[ParentTaskSection],
        source: SourceDocument,
    ) -> list[ChunkRecord]:
        parent_map = {parent.section_id: parent for parent in parents}
        records: list[ChunkRecord] = []
        for chunk in chunks:
            parent = parent_map[chunk.section_id]
            record = ChunkRecord(
                record_id=str(uuid4()),
                source=ChunkRecordSource(
                    doc_id=chunk.doc_id,
                    uri=source.source_uri,
                    type=source.source_type,
                    page_from=chunk.page_from,
                    page_to=chunk.page_to,
                ),
                unit=ChunkRecordUnit(
                    parent_id=parent.section_id,
                    chunk_id=chunk.chunk_id,
                    chunk_type=chunk.chunk_type,
                ),
                text=ChunkRecordText(
                    title=parent.title,
                    breadcrumbs=list(chunk.breadcrumbs or parent.breadcrumbs),
                    content=chunk.chunk_text,
                    summary=chunk.odgovor or parent.odgovor,
                    q=chunk.pitanje or parent.pitanje,
                ),
                metadata={
                    **source.metadata,
                    "section_id": parent.section_id,
                    "keywords": parent.keywords,
                },
                embedding=ChunkRecordEmbedding(
                    vector=list(chunk.embedding),
                    model=self.config.embedding.model,
                    input_text=chunk.embedding_input,
                ),
            )
            records.append(record)
        return records

    def run(self, file_path: str, metadata: dict[str, object] | None = None) -> IngestStats:
        metadata = dict(metadata or {})
        state_store = JsonStateStore(self.config.state_cache_path)
        source_key = str(Path(file_path).resolve())
        source_hash = sha256_file(file_path)
        if state_store.get(source_key) == source_hash:
            return IngestStats(source_uri=source_key, doc_id="", skipped_as_unchanged=True)

        extraction = self._choose_extractor(file_path, metadata)
        state = self._to_state(extraction)
        state.source.metadata.update(metadata)

        stats = IngestStats(source_uri=state.source.source_uri, doc_id=state.source.doc_id, images_total=len(state.images))

        images = enrich_images_with_vision(
            state.images,
            settings=self.config,
            doc_title=state.source.title,
            nearest_heading_map=self._nearest_heading_map(extraction),
        )
        merged_blocks = merge_image_descriptions(state.blocks, images)
        compute_breadcrumbs(merged_blocks)
        state.blocks = merged_blocks

        chunker = get_chunker(self.config.chunking.mode)
        chunking_result = chunker.chunk(
            merged_blocks,
            doc_id=state.source.doc_id,
            metadata=state.source.metadata,
            settings=self.config,
        )
        parents = enrich_parent_sections(chunking_result.parents, self.config)
        chunks = chunking_result.chunks
        chunks = embed_child_chunks(chunks, parents, self.config)
        records = self._to_records(chunks, parents, state.source)
        writer = self._build_writer()
        result: WriteResult = writer.write(records)

        state_store.set(source_key, source_hash)
        state_store.flush()

        stats.parents_total = len(parents)
        stats.children_total = len(chunks)
        stats.uploaded_rows = result.written
        return stats


def run_pipeline(file_path: str, metadata: dict[str, object] | None = None, config_path: str | None = None) -> IngestStats:
    configure_logging()
    runner = PipelineRunner(load_config(config_path))
    return runner.run(file_path, metadata)
