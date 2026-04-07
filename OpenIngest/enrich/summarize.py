from __future__ import annotations

import json
import logging

from openai import OpenAI

from OpenIngest.config import Settings
from OpenIngest.models import ParentTaskSection
from OpenIngest.utils import retry_with_backoff


logger = logging.getLogger("openingest.summarize")


def _summarize_parent(client: OpenAI, settings: Settings, parent: ParentTaskSection) -> ParentTaskSection:
    prompt = settings.enrichment.prompt.summarize
    language_instruction = f"Odgovaraj na jeziku: {settings.language}." if settings.language != "auto" else "Odgovaraj na jeziku dokumenta."
    system_text = "Respond in the language requested by the user and return valid JSON only."

    def _call() -> ParentTaskSection:
        response = client.responses.create(
            model=settings.summarize_model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_text", "text": language_instruction},
                        {
                            "type": "input_text",
                            "text": f"Naslov: {parent.title}\n\nSadržaj:\n{parent.parent_text}",
                        },
                    ],
                },
            ],
            temperature=0.2,
        )
        content = (response.output_text or "{}").strip()
        parsed = json.loads(content)
        parent.pitanje = parsed.get("PITANJE", parsed.get("q", "Kako da izvršim ovaj postupak?")).strip()
        parent.odgovor = parsed.get("ODGOVOR", parsed.get("summary", "Sažetak nije dostupan.")).strip()
        keywords = parsed.get("KEYWORDS", parsed.get("keywords", []))
        parent.keywords = [str(item).strip() for item in keywords if str(item).strip()]
        return parent

    return retry_with_backoff(
        _call,
        max_retries=settings.openai_max_retries,
        initial_backoff_seconds=settings.openai_initial_backoff_seconds,
        retry_exceptions=(Exception,),
    )


def enrich_parent_sections(parents: list[ParentTaskSection], settings: Settings) -> list[ParentTaskSection]:
    if not parents:
        return []
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for summarization")

    client = OpenAI(api_key=settings.openai_api_key)
    enriched = [_summarize_parent(client, settings, parent) for parent in parents]
    logger.info("Summarized %s parent sections", len(enriched))
    return enriched
