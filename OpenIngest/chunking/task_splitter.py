from __future__ import annotations

import re
from uuid import uuid4

from OpenIngest.config import Settings
from OpenIngest.defaults import DEFAULT_CHUNKING
from OpenIngest.models import ChildChunk, ExtractedImage, ParentTaskSection, StructuredBlock
from OpenIngest.utils import estimate_tokens


def merge_image_descriptions(blocks: list[StructuredBlock], images: list[ExtractedImage]) -> list[StructuredBlock]:
    image_map = {image.image_id: image for image in images}
    merged: list[StructuredBlock] = []
    for block in blocks:
        if block.type != "image_anchor" or not block.anchor_image_id:
            merged.append(block)
            continue
        image = image_map.get(block.anchor_image_id)
        vision_text = (image.vision_text if image else "") or "Slika bez opisa."
        merged.append(
            StructuredBlock(
                block_id=str(uuid4()),
                type="paragraph",
                text=f"[OPIS SLIKE {block.anchor_image_id}] {vision_text}",
                page_from=block.page_from,
                page_to=block.page_to,
                breadcrumbs=block.breadcrumbs,
            )
        )
    return merged


def compute_breadcrumbs(blocks: list[StructuredBlock]) -> None:
    heading_stack: list[str] = []
    level_stack: list[int] = []
    for block in blocks:
        if block.type == "heading":
            level = block.level or 1
            while level_stack and level_stack[-1] >= level:
                level_stack.pop()
                heading_stack.pop()
            level_stack.append(level)
            heading_stack.append(block.text)
        block.breadcrumbs = " > ".join(heading_stack)


def _is_task_heading(block: StructuredBlock, settings: Settings) -> bool:
    if block.type != "heading":
        return False
    prefixes = tuple(("^" + re.escape(prefix)) for prefix in settings.chunking.task_heading_prefixes)
    pattern = re.compile("|".join(prefixes), re.IGNORECASE)
    return bool(pattern.search(block.text.strip()))


def detect_parent_sections(
    document_blocks: list[StructuredBlock],
    doc_id: str,
    settings: Settings,
    metadata: dict[str, object] | None = None,
) -> list[ParentTaskSection]:
    if not document_blocks:
        return []

    sections: list[ParentTaskSection] = []
    current_title = "Opći postupak"
    current_blocks: list[StructuredBlock] = []
    current_breadcrumbs: list[str] = []

    def _flush() -> None:
        nonlocal current_blocks, current_title, current_breadcrumbs
        if not current_blocks:
            return
        page_from_values = [block.page_from for block in current_blocks if block.page_from is not None]
        page_to_values = [block.page_to for block in current_blocks if block.page_to is not None]
        text = "\n".join(block.text for block in current_blocks if block.text.strip())
        sections.append(
            ParentTaskSection(
                section_id=str(uuid4()),
                doc_id=doc_id,
                title=current_title,
                breadcrumbs=current_breadcrumbs,
                page_from=min(page_from_values) if page_from_values else None,
                page_to=max(page_to_values) if page_to_values else None,
                parent_text=text,
                metadata=dict(metadata or {}),
            )
        )
        current_blocks = []

    for block in document_blocks:
        starts_task = _is_task_heading(block, settings)
        if starts_task and current_blocks:
            _flush()
            current_title = block.text
            current_breadcrumbs = [part for part in (block.breadcrumbs or "").split(" > ") if part]
            continue

        if block.type == "heading" and not current_blocks:
            current_title = block.text
            current_breadcrumbs = [part for part in (block.breadcrumbs or "").split(" > ") if part]
            continue

        current_blocks.append(block)

    _flush()
    return sections


def _classify_chunk_type(text: str, settings: Settings) -> str:
    low = text.lower()
    if any(k in low for k in settings.chunking.prereq_keywords):
        return "prereq"
    if any(k in low for k in settings.chunking.troubleshooting_keywords):
        return "troubleshooting"
    if any(k in low for k in settings.chunking.example_keywords):
        return "example"
    if re.match(r"^\d+[\.)]", text.strip()):
        return "steps"
    return "task"


def _chunk_lines_with_overlap(lines: list[str], settings: Settings) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for line in lines:
        line_tokens = estimate_tokens(line)
        if current and current_tokens + line_tokens > settings.chunk_hard_cap_tokens:
            chunks.append(current)
            overlap = current[-2:] if len(current) > 2 else current[-1:]
            current = overlap + [line]
            current_tokens = sum(estimate_tokens(item) for item in current)
            continue
        current.append(line)
        current_tokens += line_tokens
        if current_tokens >= settings.chunk_target_tokens:
            chunks.append(current)
            current = []
            current_tokens = 0

    if current:
        chunks.append(current)
    return chunks


def build_child_chunks(parents: list[ParentTaskSection], settings: Settings) -> list[ChildChunk]:
    chunks: list[ChildChunk] = []
    for parent in parents:
        raw_lines = [line.strip() for line in parent.parent_text.splitlines() if line.strip()]
        if not raw_lines:
            continue
        line_groups = _chunk_lines_with_overlap(raw_lines, settings)
        for group in line_groups:
            text = "\n".join(group)
            chunks.append(
                ChildChunk(
                    chunk_id=str(uuid4()),
                    section_id=parent.section_id,
                    doc_id=parent.doc_id,
                    chunk_type=_classify_chunk_type(text, settings),
                    chunk_text=text,
                    breadcrumbs=parent.breadcrumbs,
                    page_from=parent.page_from,
                    page_to=parent.page_to,
                    metadata=dict(parent.metadata),
                )
            )
    return chunks
