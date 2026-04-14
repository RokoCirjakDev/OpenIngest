from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from OpenIngest.models import EnrichedDocument, ExtractedImage, ExtractionResult, StructuredBlock


_KEY_ACTION_PATTERN = re.compile(r"\b(F\d{1,2}|TAB|ENTER|ESC|CTRL\+[A-Z]|ALT\+[A-Z]|SHIFT\+[A-Z]|N)\b", re.IGNORECASE)
_CONSTRAINT_PATTERN = re.compile(
    r"\b(mora|morate|mora biti|neće dopustiti|nije dopušteno|samo ako|samo|uvjet|obavezno|sumaran iznos)\b",
    re.IGNORECASE,
)


def _iter_block_items(parent: DocxDocument):
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _looks_like_toc_entry(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    return bool(
        normalized
        and re.match(r"^\d+(?:\.\d+)*\.?\s+.+\s+\d+$", normalized)
        and len(normalized.split()) <= 12
    )


def _looks_like_heading(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized or len(normalized) > 120:
        return False
    if normalized[-1] in ".:;!?":
        return False
    if len(normalized.split()) > 10:
        return False
    if _looks_like_toc_entry(normalized):
        return False
    return True


def _infer_paragraph_type(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if re.match(r"^\d+(?:\.\d+)*[\.)]?\s+", normalized):
        return "list_item"
    if " > " in normalized or "→" in normalized:
        return "note"
    if _KEY_ACTION_PATTERN.search(normalized):
        return "note"
    if _CONSTRAINT_PATTERN.search(normalized):
        return "note"
    return "paragraph"


def _extract_images_from_paragraph(paragraph: Paragraph, *, doc_id: str, ordinal_start: int):
    images: list[ExtractedImage] = []
    blocks: list[StructuredBlock] = []
    ordinal = ordinal_start

    for run in paragraph.runs:
        drawing_elements = run._element.xpath(".//*[local-name()='blip']")
        for drawing in drawing_elements:
            rel_id = drawing.get(qn("r:embed"))
            if not rel_id:
                continue
            image_part = paragraph.part.related_parts[rel_id]
            image_bytes = image_part.blob
            image_id = str(uuid4())
            anchor = f"[[IMAGE:{image_id}]]"
            images.append(
                ExtractedImage(
                    image_id=image_id,
                    source_doc_id=doc_id,
                    page=None,
                    ordinal=ordinal,
                    bytes=image_bytes,
                    mime_type=image_part.content_type,
                    anchor=anchor,
                )
            )
            blocks.append(
                StructuredBlock(
                    block_id=str(uuid4()),
                    type="image_anchor",
                    text=anchor,
                    anchor_image_id=image_id,
                )
            )
            ordinal += 1

    return blocks, images, ordinal


def extract_docx(file_path: str, metadata: dict[str, object] | None = None) -> ExtractionResult:
    path_obj = Path(file_path)
    doc_id = str(uuid4())
    document = Document(file_path)
    blocks: list[StructuredBlock] = []
    images: list[ExtractedImage] = []
    image_ordinal = 0

    for block_item in _iter_block_items(document):
        if isinstance(block_item, Paragraph):
            style_name = (block_item.style.name or "").lower() if block_item.style else ""
            text = block_item.text.strip()
            if not text or _looks_like_toc_entry(text):
                continue
            if style_name.startswith("heading") and text:
                level_digits = "".join(ch for ch in style_name if ch.isdigit())
                level = int(level_digits) if level_digits else 1
                blocks.append(
                    StructuredBlock(
                        block_id=str(uuid4()),
                        type="heading",
                        text=text,
                        level=max(1, min(6, level)),
                    )
                )
            else:
                if _looks_like_heading(text):
                    blocks.append(
                        StructuredBlock(
                            block_id=str(uuid4()),
                            type="heading",
                            text=text,
                            level=1,
                        )
                    )
                else:
                    blocks.append(
                        StructuredBlock(
                            block_id=str(uuid4()),
                            type=_infer_paragraph_type(text),
                            text=text,
                        )
                    )

                paragraph_blocks, paragraph_images, image_ordinal = _extract_images_from_paragraph(
                    block_item,
                    doc_id=doc_id,
                    ordinal_start=image_ordinal,
                )
                blocks.extend(paragraph_blocks)
                images.extend(paragraph_images)
        elif isinstance(block_item, Table):
            rows = []
            for row in block_item.rows:
                rows.append(" | ".join(cell.text.strip() for cell in row.cells))
            table_text = "\n".join(filter(None, rows)).strip()
            if table_text:
                blocks.append(
                    StructuredBlock(
                        block_id=str(uuid4()),
                        type="table",
                        text=table_text,
                    )
                )

    enriched_doc = EnrichedDocument(
        doc_id=doc_id,
        source_uri=str(path_obj),
        title=path_obj.stem,
        blocks=blocks,
        metadata=dict(metadata or {}),
    )
    return ExtractionResult(document=enriched_doc, images=images)
