from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI

from OpenIngest.config import CustomSummarizerFieldConfig, Settings
from OpenIngest.models import ChildChunk, ParentTaskSection
from OpenIngest.utils import estimate_tokens, retry_with_backoff


logger = logging.getLogger("openingest.summarize")

_BASE_CHUNK_KEYS: tuple[str, ...] = (
    "PITANJE",
    "ODGOVOR",
    "STEPS",
    "KEYWORDS",
    "CONSTRAINTS",
    "PREREQUISITES",
    "SYSTEM_EFFECTS",
    "BRANCHES",
    "NAVIGATION_PATHS",
    "CROSS_SYSTEM_REFS",
    "ERROR_SCENARIOS",
    "EMPHASIS_SIGNALS",
)


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


def _custom_fields_system_instructions(custom_fields: list[CustomSummarizerFieldConfig]) -> str:
    if not custom_fields:
        return ""

    lines = [
        "Also include custom fields exactly as configured.",
        "Custom field requirements:",
    ]
    for custom_field in custom_fields:
        if custom_field.type == "enum":
            options = ", ".join(custom_field.options)
            lines.append(
                f"- {custom_field.name}: return a single string and it must be one of [{options}]. Description: {custom_field.description}"
            )
        elif custom_field.type == "freelist":
            lines.append(
                f"- {custom_field.name}: return an array of strings built according to this description: {custom_field.description}"
            )
        else:
            lines.append(
                f"- {custom_field.name}: return a single paragraph string built according to this description: {custom_field.description}"
            )
        if custom_field.required:
            lines.append(f"  {custom_field.name} is required and must not be empty.")
    return " ".join(lines)


def _custom_fields_json_shape(custom_fields: list[CustomSummarizerFieldConfig]) -> str:
    if not custom_fields:
        return ""

    shape_parts: list[str] = []
    for custom_field in custom_fields:
        if custom_field.type == "enum":
            options = " | ".join(custom_field.options)
            shape_parts.append(f'"{custom_field.name}": "{options}"')
        elif custom_field.type == "freelist":
            shape_parts.append(f'"{custom_field.name}": ["..."]')
        else:
            shape_parts.append(f'"{custom_field.name}": "..."')
    return ", " + ", ".join(shape_parts)


def _validate_custom_fields(
    parsed: dict[str, Any],
    custom_fields: list[CustomSummarizerFieldConfig],
    chunk: ChildChunk,
) -> dict[str, str | list[str]]:
    validated: dict[str, str | list[str]] = {}

    for custom_field in custom_fields:
        value = parsed.get(custom_field.name)
        if value is None:
            if custom_field.required:
                raise ValueError(
                    f"Chunk enrichment missing required custom field '{custom_field.name}' for chunk {chunk.chunk_id} (section {chunk.section_id})."
                )
            continue

        if custom_field.type == "enum":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Custom field '{custom_field.name}' must be a non-empty string for chunk {chunk.chunk_id} (section {chunk.section_id})."
                )
            selected = value.strip()
            if selected not in custom_field.options:
                raise ValueError(
                    f"Custom field '{custom_field.name}' must be one of {custom_field.options} for chunk {chunk.chunk_id} (section {chunk.section_id}); received '{selected}'."
                )
            validated[custom_field.name] = selected
            continue

        if custom_field.type == "freelist":
            if not isinstance(value, list):
                raise ValueError(
                    f"Custom field '{custom_field.name}' must be a list for chunk {chunk.chunk_id} (section {chunk.section_id})."
                )
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if custom_field.required and not cleaned:
                raise ValueError(
                    f"Custom field '{custom_field.name}' is required and must contain at least one non-empty list item for chunk {chunk.chunk_id} (section {chunk.section_id})."
                )
            validated[custom_field.name] = cleaned
            continue

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Custom field '{custom_field.name}' must be a non-empty string paragraph for chunk {chunk.chunk_id} (section {chunk.section_id})."
            )
        validated[custom_field.name] = value.strip()

    return validated


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
    custom_fields = list(settings.enrichment.custom_fields or [])
    allowed_keys = list(_BASE_CHUNK_KEYS) + [custom_field.name for custom_field in custom_fields]
    custom_keys_part = _custom_fields_system_instructions(custom_fields)
    custom_json_shape_part = _custom_fields_json_shape(custom_fields)
    language_instruction = f"Odgovaraj na jeziku: {settings.language}." if settings.language != "auto" else "Odgovaraj na jeziku dokumenta."
    system_text = (
        "Return valid JSON only. "
        f"The JSON must contain exactly these keys: {', '.join(allowed_keys)}. "
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
        "EMPHASIS_SIGNALS must include repeated/critical actions or warnings that appear emphasized. "
        f"{custom_keys_part}"
    )

    def _call() -> ChildChunk:
        logger.info(
            "Enriching chunk %s/%s section=%s type=%s chars=%s tokens~=%s custom_fields=%s",
            chunk.chunk_id,
            parent.section_id,
            parent.section_id,
            chunk.chunk_type,
            len(chunk.chunk_text or ""),
            estimate_tokens(chunk.chunk_text or ""),
            ",".join(field.name for field in custom_fields) if custom_fields else "none",
        )
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
                                f'"ERROR_SCENARIOS": ["..."], "EMPHASIS_SIGNALS": ["..."]{custom_json_shape_part}}}'
                            ),
                        },
                    ],
                },
            ],
            temperature=0.1,
        )

        content = (response.output_text or "").strip()
        logger.info(
            "Received chunk enrichment response for chunk %s section=%s chars=%s",
            chunk.chunk_id,
            chunk.section_id,
            len(content),
        )
        if not content:
            raise ValueError(
                f"Chunk keyword generation returned empty output for chunk {chunk.chunk_id} (section {chunk.section_id})."
            )

        content = _extract_pure_json(content)
        logger.info(
            "Parsed chunk enrichment JSON candidate for chunk %s section=%s chars=%s",
            chunk.chunk_id,
            chunk.section_id,
            len(content),
        )
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
        custom_values = _validate_custom_fields(parsed, custom_fields, chunk)
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
        chunk.custom_fields = custom_values
        chunk.metadata["keywords"] = clean_keywords
        logger.info(
            "Finished chunk %s section=%s keywords=%s custom_fields=%s",
            chunk.chunk_id,
            chunk.section_id,
            len(clean_keywords),
            list(custom_values.keys()) if custom_values else [],
        )
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

    total_chunks = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        parent = parent_map.get(chunk.section_id)
        if parent is None:
            raise ValueError(
                f"Chunk enrichment cannot find parent section {chunk.section_id} for chunk {chunk.chunk_id}."
            )
        logger.info(
            "Starting chunk enrichment %s/%s chunk=%s section=%s type=%s",
            index,
            total_chunks,
            chunk.chunk_id,
            chunk.section_id,
            chunk.chunk_type,
        )
        _enrich_one_chunk(client, settings, chunk, parent)
        logger.info(
            "Completed chunk enrichment %s/%s chunk=%s section=%s",
            index,
            total_chunks,
            chunk.chunk_id,
            chunk.section_id,
        )

    logger.info("Enriched %s chunks with question, summary, steps, and keywords", len(chunks))
    return chunks
