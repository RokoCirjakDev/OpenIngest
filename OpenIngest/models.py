from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


BlockType = Literal[
    "heading",
    "paragraph",
    "list_item",
    "code",
    "image_anchor",
    "table",
    "note",
]

ListKind = Literal["ordered", "unordered"]
ChunkType = Literal["prereq", "steps", "example", "troubleshooting", "reference", "task"]


@dataclass(slots=True)
class ExtractedImage:
    image_id: str
    source_doc_id: str
    page: int | None
    ordinal: int
    bytes: bytes
    mime_type: str
    anchor: str
    caption: str | None = None
    vision_text: str | None = None
    hash_sha256: str | None = None


@dataclass(slots=True)
class StructuredBlock:
    block_id: str
    type: BlockType
    text: str = ""
    level: int | None = None
    list_kind: ListKind | None = None
    page_from: int | None = None
    page_to: int | None = None
    breadcrumbs: str | None = None
    anchor_image_id: str | None = None


@dataclass(slots=True)
class EnrichedDocument:
    doc_id: str
    source_uri: str
    title: str
    blocks: list[StructuredBlock]
    metadata: dict[str, Any] = field(default_factory=dict)
    full_text_enriched: str | None = None
    doc_hash_sha256: str | None = None


@dataclass(slots=True)
class ParentTaskSection:
    section_id: str
    doc_id: str
    title: str
    breadcrumbs: list[str] = field(default_factory=list)
    page_from: int | None = None
    page_to: int | None = None
    parent_text: str = ""
    pitanje: str | None = None
    odgovor: str | None = None
    keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChildChunk:
    chunk_id: str
    section_id: str
    doc_id: str
    chunk_type: ChunkType
    chunk_text: str
    breadcrumbs: list[str] = field(default_factory=list)
    page_from: int | None = None
    page_to: int | None = None
    pitanje: str | None = None
    odgovor: str | None = None
    embedding_input: str | None = None
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractionResult:
    document: EnrichedDocument
    images: list[ExtractedImage]


@dataclass(slots=True)
class IngestStats:
    source_uri: str
    doc_id: str
    images_total: int = 0
    parents_total: int = 0
    children_total: int = 0
    uploaded_rows: int = 0
    openai_tokens_in: int = 0
    openai_tokens_out: int = 0
    openai_calls: int = 0
    skipped_as_unchanged: bool = False


@dataclass(slots=True)
class SourceDocument:
    doc_id: str
    source_uri: str
    source_type: str
    title: str
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChunkRecordText:
    title: str = ""
    breadcrumbs: list[str] = field(default_factory=list)
    content: str = ""
    summary: str | None = None
    q: str | None = None


@dataclass(slots=True)
class ChunkRecordSource:
    doc_id: str
    uri: str
    type: str
    page_from: int | None = None
    page_to: int | None = None


@dataclass(slots=True)
class ChunkRecordUnit:
    parent_id: str
    chunk_id: str
    chunk_type: ChunkType


@dataclass(slots=True)
class ChunkRecordEmbedding:
    vector: list[float] = field(default_factory=list)
    model: str | None = None
    input_text: str | None = None


@dataclass(slots=True)
class ChunkRecord:
    record_id: str
    source: ChunkRecordSource
    unit: ChunkRecordUnit
    text: ChunkRecordText
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: ChunkRecordEmbedding = field(default_factory=ChunkRecordEmbedding)


@dataclass(slots=True)
class PipelineArtifact:
    name: str
    version: str
    payload: Any


@dataclass(slots=True)
class PipelineState:
    source: SourceDocument
    blocks: list[StructuredBlock] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)
    parents: list[ParentTaskSection] = field(default_factory=list)
    chunks: list[ChildChunk] = field(default_factory=list)
    records: list[ChunkRecord] = field(default_factory=list)
    artifacts: list[PipelineArtifact] = field(default_factory=list)
