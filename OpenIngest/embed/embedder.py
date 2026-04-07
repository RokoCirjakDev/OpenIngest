from __future__ import annotations

import logging

from openai import OpenAI

from OpenIngest.config import Settings
from OpenIngest.models import ChildChunk, ParentTaskSection
from OpenIngest.utils import retry_with_backoff


logger = logging.getLogger("openingest.embed")


def _embedding_input(chunk: ChildChunk, parent_map: dict[str, ParentTaskSection]) -> str:
    parent = parent_map[chunk.section_id]
    pitanje = parent.pitanje or "Kako da izvršim ovaj zadatak?"
    odgovor = parent.odgovor or "Sažetak nije dostupan."
    return f"{pitanje}\n{odgovor}\n\n{chunk.chunk_text}"


def embed_child_chunks(
    chunks: list[ChildChunk],
    parent_sections: list[ParentTaskSection],
    settings: Settings,
) -> list[ChildChunk]:
    if not chunks:
        return []
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for embedding")

    client = OpenAI(api_key=settings.openai_api_key)
    parent_map = {parent.section_id: parent for parent in parent_sections}

    for chunk in chunks:
        chunk.embedding_input = _embedding_input(chunk, parent_map)

        def _call() -> list[float]:
            response = client.embeddings.create(
                model=settings.embedding_model,
                input=chunk.embedding_input,
            )
            return list(response.data[0].embedding)

        chunk.embedding = retry_with_backoff(
            _call,
            max_retries=settings.openai_max_retries,
            initial_backoff_seconds=settings.openai_initial_backoff_seconds,
            retry_exceptions=(Exception,),
        )

    logger.info("Embedded %s chunks", len(chunks))
    return chunks
