from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from openai import OpenAI

from OpenIngest.config import Settings
from OpenIngest.models import ExtractedImage
from OpenIngest.utils import JsonStateStore, retry_with_backoff, sha256_bytes


logger = logging.getLogger("openingest.vision")

def _build_context(doc_title: str, nearest_heading: str | None, caption: str | None) -> str:
    parts = [f"Naslov dokumenta: {doc_title}"]
    if nearest_heading:
        parts.append(f"Najbliži naslov: {nearest_heading}")
    if caption:
        parts.append(f"Natpis slike: {caption}")
    return "\n".join(parts)


def _vision_one(
    client: OpenAI,
    image: ExtractedImage,
    settings: Settings,
    doc_title: str,
    nearest_heading: str | None,
) -> str:
    payload_context = _build_context(doc_title, nearest_heading, image.caption)
    b64 = base64.b64encode(image.bytes).decode("utf-8")
    prompt = settings.enrichment.prompt.image_caption
    language_instruction = f"Odgovori na jeziku: {settings.language}." if settings.language != "auto" else "Odgovori na jeziku dokumenta."

    def _call() -> str:
        response = client.responses.create(
            model=settings.vision_model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": "Describe the image clearly and follow the requested language."}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_text", "text": language_instruction},
                        {"type": "input_text", "text": payload_context},
                        {
                            "type": "input_image",
                            "image_url": f"data:{image.mime_type};base64,{b64}",
                        },
                    ],
                },
            ],
            temperature=0.2,
        )
        return (response.output_text or "").strip()

    return retry_with_backoff(
        _call,
        max_retries=settings.openai_max_retries,
        initial_backoff_seconds=settings.openai_initial_backoff_seconds,
        retry_exceptions=(Exception,),
    )


def enrich_images_with_vision(
    images: Iterable[ExtractedImage],
    *,
    settings: Settings,
    doc_title: str,
    nearest_heading_map: dict[str, str] | None = None,
) -> list[ExtractedImage]:
    nearest_heading_map = nearest_heading_map or {}
    image_list = list(images)
    if not image_list:
        return []

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for vision enrichment")

    client = OpenAI(api_key=settings.openai_api_key)
    cache = JsonStateStore(settings.image_cache_path)

    def _worker(img: ExtractedImage) -> ExtractedImage:
        image_hash = sha256_bytes(img.bytes)
        img.hash_sha256 = image_hash
        cached = cache.get(image_hash)
        if isinstance(cached, str) and cached.strip():
            img.vision_text = cached
            return img

        heading = nearest_heading_map.get(img.image_id)
        vision_text = _vision_one(client, img, settings, doc_title, heading)
        img.vision_text = vision_text
        cache.set(image_hash, vision_text)
        return img

    with ThreadPoolExecutor(max_workers=max(1, settings.vision_max_workers)) as pool:
        enriched = list(pool.map(_worker, image_list))

    cache.flush()
    logger.info("Vision enriched %s images", len(enriched))
    return enriched
