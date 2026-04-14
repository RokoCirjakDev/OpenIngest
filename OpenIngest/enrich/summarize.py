from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from OpenIngest.config import Settings
from OpenIngest.models import ChildChunk, ParentTaskSection
from OpenIngest.utils import retry_with_backoff


logger = logging.getLogger("openingest.summarize")


def _extract_pure_json(content: str) -> str:
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1].strip()

    return text


def _summarize_parent(client: OpenAI, settings: Settings, parent: ParentTaskSection) -> ParentTaskSection:
    prompt = settings.enrichment.prompt.summarize
    language_instruction = f"Odgovaraj na jeziku: {settings.language}." if settings.language != "auto" else "Odgovaraj na jeziku dokumenta."
    system_text = (
        "Respond in the language requested by the user and return valid JSON only. "
        "The JSON must contain exactly these keys: PITANJE, ODGOVOR, KEYWORDS. "
        "Do not output any other top-level keys such as Sažetak or summary."
    )

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
                            "text": (
                                f"Naslov: {parent.title}\n\nSadržaj:\n{parent.parent_text}\n\n"
                                "Return only this JSON shape:\n"
                                '{"PITANJE": "...", "ODGOVOR": "...", "KEYWORDS": ["...", "..."]}'
                            ),
                        },
                    ],
                },
            ],
            temperature=0.2,
        )
        content = (response.output_text or "").strip()
        if not content:
            raise ValueError(
                f"Summarization returned empty output for section {parent.section_id}; expected JSON with PITANJE, ODGOVOR, and KEYWORDS."
            )

        content = _extract_pure_json(content)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Summarization returned invalid JSON for section {parent.section_id} ({type(exc).__name__}: {exc}). Raw output: {content}"
            ) from exc
        pitanje = parsed.get("PITANJE")
        odgovor = parsed.get("ODGOVOR")
        keywords = parsed.get("KEYWORDS")

        if not isinstance(pitanje, str) or not pitanje.strip():
            raise ValueError(
                f"Summarization response missing non-empty PITANJE for section {parent.section_id}. Parsed keys: {list(parsed.keys())}."
            )
        if not isinstance(odgovor, str) or not odgovor.strip():
            raise ValueError(
                f"Summarization response missing non-empty ODGOVOR for section {parent.section_id}. Parsed keys: {list(parsed.keys())}."
            )
        if not isinstance(keywords, list):
            raise ValueError(
                f"Summarization response missing KEYWORDS list for section {parent.section_id}. Parsed keys: {list(parsed.keys())}."
            )

        parent.pitanje = pitanje.strip()
        parent.odgovor = odgovor.strip()
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
        raise ValueError("Summarization cannot run because OPENAI_API_KEY is not set in the current environment or config.")

    client = OpenAI(api_key=settings.openai_api_key)
    enriched = [_summarize_parent(client, settings, parent) for parent in parents]
    logger.info("Summarized %s parent sections", len(enriched))
    return enriched


def _enrich_one_chunk(client: OpenAI, settings: Settings, chunk: ChildChunk, parent: ParentTaskSection) -> ChildChunk:
    prompt = settings.enrichment.prompt.summarize
    language_instruction = f"Odgovaraj na jeziku: {settings.language}." if settings.language != "auto" else "Odgovaraj na jeziku dokumenta."
    system_text = (
        "Return valid JSON only. "
        "The JSON must contain exactly these keys: PITANJE, ODGOVOR, STEPS, KEYWORDS, CONSTRAINTS, PREREQUISITES, "
        "SYSTEM_EFFECTS, BRANCHES, NAVIGATION_PATHS, CROSS_SYSTEM_REFS, ERROR_SCENARIOS, EMPHASIS_SIGNALS. "
        "PITANJE must be a concise search question. "
        "ODGOVOR must be a knowledgeable explanation in 2-4 sentences without an explicit numbered list. "
        "STEPS must be an array of exact ordered action steps extracted from the chunk content; "
        "if no actionable sequence exists, STEPS must be an empty array. "
        "KEYWORDS must be an array of concise keywords extracted from this chunk only. "
        "CONSTRAINTS must include hard validation rules and required conditions. "
        "PREREQUISITES must include required prior actions and dependencies. "
        "SYSTEM_EFFECTS must include state/accounting/system outcome changes after actions. "
        "BRANCHES must include decision points and alternative paths with trigger condition text. "
        "NAVIGATION_PATHS must include menu and navigation routes exactly as described. "
        "CROSS_SYSTEM_REFS must include interactions between systems/modules. "
        "ERROR_SCENARIOS must include problem/failure scenarios and remediation from the chunk. "
        "EMPHASIS_SIGNALS must include repeated/critical actions or warnings that appear emphasized."
    )

    def _call() -> ChildChunk:
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
                            "text": (
                                f"Naslov sekcije: {parent.title}\n"
                                f"Tip chunka: {chunk.chunk_type}\n\n"
                                f"Sadržaj chunka:\n{chunk.chunk_text}\n\n"
                                "Vrati samo JSON:\n"
                                '{"PITANJE": "...", "ODGOVOR": "...", "STEPS": ["..."], "KEYWORDS": ["..."], '
                                '"CONSTRAINTS": ["..."], "PREREQUISITES": ["..."], "SYSTEM_EFFECTS": ["..."], '
                                '"BRANCHES": ["..."] , "NAVIGATION_PATHS": ["..."], "CROSS_SYSTEM_REFS": ["..."], '
                                '"ERROR_SCENARIOS": ["..."], "EMPHASIS_SIGNALS": ["..."]}'
                            ),
                        },
                    ],
                },
            ],
            temperature=0.1,
        )

        content = (response.output_text or "").strip()
        if not content:
            raise ValueError(
                f"Chunk keyword generation returned empty output for chunk {chunk.chunk_id} (section {chunk.section_id})."
            )

        content = _extract_pure_json(content)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Chunk enrichment returned invalid JSON for chunk {chunk.chunk_id} (section {chunk.section_id}) "
                f"({type(exc).__name__}: {exc}). Raw output: {content}"
            ) from exc

        pitanje = parsed.get("PITANJE")
        odgovor = parsed.get("ODGOVOR")
        steps = parsed.get("STEPS")
        keywords = parsed.get("KEYWORDS")
        constraints = parsed.get("CONSTRAINTS")
        prerequisites = parsed.get("PREREQUISITES")
        system_effects = parsed.get("SYSTEM_EFFECTS")
        branches = parsed.get("BRANCHES")
        navigation_paths = parsed.get("NAVIGATION_PATHS")
        cross_system_refs = parsed.get("CROSS_SYSTEM_REFS")
        error_scenarios = parsed.get("ERROR_SCENARIOS")
        emphasis_signals = parsed.get("EMPHASIS_SIGNALS")

        if not isinstance(pitanje, str) or not pitanje.strip():
            raise ValueError(
                f"Chunk enrichment missing non-empty PITANJE for chunk {chunk.chunk_id} (section {chunk.section_id}). "
                f"Parsed keys: {list(parsed.keys())}."
            )
        if not isinstance(odgovor, str) or not odgovor.strip():
            raise ValueError(
                f"Chunk enrichment missing non-empty ODGOVOR for chunk {chunk.chunk_id} (section {chunk.section_id}). "
                f"Parsed keys: {list(parsed.keys())}."
            )
        if not isinstance(steps, list):
            raise ValueError(
                f"Chunk enrichment missing STEPS list for chunk {chunk.chunk_id} (section {chunk.section_id}). "
                f"Parsed keys: {list(parsed.keys())}."
            )
        if not isinstance(keywords, list):
            raise ValueError(
                f"Chunk enrichment missing KEYWORDS list for chunk {chunk.chunk_id} (section {chunk.section_id}). "
                f"Parsed keys: {list(parsed.keys())}."
            )
        list_fields = {
            "CONSTRAINTS": constraints,
            "PREREQUISITES": prerequisites,
            "SYSTEM_EFFECTS": system_effects,
            "BRANCHES": branches,
            "NAVIGATION_PATHS": navigation_paths,
            "CROSS_SYSTEM_REFS": cross_system_refs,
            "ERROR_SCENARIOS": error_scenarios,
            "EMPHASIS_SIGNALS": emphasis_signals,
        }
        for field_name, value in list_fields.items():
            if not isinstance(value, list):
                raise ValueError(
                    f"Chunk enrichment missing {field_name} list for chunk {chunk.chunk_id} (section {chunk.section_id}). "
                    f"Parsed keys: {list(parsed.keys())}."
                )

        clean_steps = [str(item).strip() for item in steps if str(item).strip()]
        clean_keywords = [str(item).strip() for item in keywords if str(item).strip()]
        clean_constraints = [str(item).strip() for item in constraints if str(item).strip()]
        clean_prerequisites = [str(item).strip() for item in prerequisites if str(item).strip()]
        clean_system_effects = [str(item).strip() for item in system_effects if str(item).strip()]
        clean_branches = [str(item).strip() for item in branches if str(item).strip()]
        clean_navigation_paths = [str(item).strip() for item in navigation_paths if str(item).strip()]
        clean_cross_system_refs = [str(item).strip() for item in cross_system_refs if str(item).strip()]
        clean_error_scenarios = [str(item).strip() for item in error_scenarios if str(item).strip()]
        clean_emphasis_signals = [str(item).strip() for item in emphasis_signals if str(item).strip()]
        if not clean_keywords:
            raise ValueError(
                f"Chunk enrichment produced empty KEYWORDS for chunk {chunk.chunk_id} (section {chunk.section_id})."
            )

        chunk.pitanje = pitanje.strip()
        chunk.odgovor = odgovor.strip()
        chunk.steps = clean_steps
        chunk.constraints = clean_constraints
        chunk.prerequisites = clean_prerequisites
        chunk.system_effects = clean_system_effects
        chunk.branches = clean_branches
        chunk.navigation_paths = clean_navigation_paths
        chunk.cross_system_refs = clean_cross_system_refs
        chunk.error_scenarios = clean_error_scenarios
        chunk.emphasis_signals = clean_emphasis_signals
        chunk.metadata["keywords"] = clean_keywords
        return chunk

    return retry_with_backoff(
        _call,
        max_retries=settings.openai_max_retries,
        initial_backoff_seconds=settings.openai_initial_backoff_seconds,
        retry_exceptions=(Exception,),
    )


def enrich_chunks(
    chunks: list[ChildChunk],
    parents: list[ParentTaskSection],
    settings: Settings,
) -> list[ChildChunk]:
    if not chunks:
        return []
    if not settings.openai_api_key:
        raise ValueError("Chunk enrichment cannot run because OPENAI_API_KEY is not set in the current environment or config.")

    parent_map = {parent.section_id: parent for parent in parents}
    client = OpenAI(api_key=settings.openai_api_key)

    for chunk in chunks:
        parent = parent_map.get(chunk.section_id)
        if parent is None:
            raise ValueError(
                f"Chunk enrichment cannot find parent section {chunk.section_id} for chunk {chunk.chunk_id}."
            )
        _enrich_one_chunk(client, settings, chunk, parent)

    logger.info("Enriched %s chunks with question, summary, steps, and keywords", len(chunks))
    return chunks
