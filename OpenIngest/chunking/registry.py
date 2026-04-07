from __future__ import annotations

from OpenIngest.chunking.base import Chunker
from OpenIngest.chunking.procedure import ProcedureChunker
from OpenIngest.chunking.semantic import SemanticChunker
from OpenIngest.chunking.structure import StructureChunker
from OpenIngest.chunking.window import SlidingWindowChunker


def get_chunker(mode: str) -> Chunker:
    key = (mode or "procedure").lower()
    if key == "procedure":
        return ProcedureChunker()
    if key == "structure":
        return StructureChunker()
    if key == "window":
        return SlidingWindowChunker()
    if key == "semantic":
        return SemanticChunker()
    return ProcedureChunker()
