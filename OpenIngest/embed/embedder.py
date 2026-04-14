from __future__ import annotations

import logging

from openai import OpenAI

from OpenIngest.config import Settings
from OpenIngest.models import ChildChunk
from OpenIngest.utils import retry_with_backoff


logger = logging.getLogger("openingest.embed")


def _embedding_input(chunk: ChildChunk) -> str:
    if not chunk.pitanje:
        raise ValueError(
            f"Cannot build embedding input for chunk {chunk.chunk_id} in section {chunk.section_id}: chunk question is missing."
        )
    if not chunk.odgovor:
        raise ValueError(
            f"Cannot build embedding input for chunk {chunk.chunk_id} in section {chunk.section_id}: chunk summary is missing."
        )
    pitanje = chunk.pitanje
    odgovor = chunk.odgovor
    return f"{pitanje}\n{odgovor}\n\n{chunk.chunk_text}"


def embed_child_chunks(
    chunks: list[ChildChunk],
    settings: Settings,
) -> list[ChildChunk]:
    if not chunks:
        return []
    if not settings.openai_api_key:
        raise ValueError("Embedding cannot run because OPENAI_API_KEY is not set in the current environment or config.")

    client = OpenAI(api_key=settings.openai_api_key)
    for chunk in chunks:
        chunk.embedding_input = _embedding_input(chunk)

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
