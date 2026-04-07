from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import fitz

from OpenIngest.config import Settings
from OpenIngest.defaults import DEFAULT_CHUNKING
from OpenIngest.models import EnrichedDocument, ExtractedImage, ExtractionResult, StructuredBlock

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None


def _ocr_page_if_needed(page: fitz.Page, text_exists: bool, ocr_language: str) -> str:
    if text_exists:
        return ""
    if pytesseract is None or Image is None:
        return ""
    pix = page.get_pixmap(dpi=220)
    image = Image.open(BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(image, lang=ocr_language).strip()


def extract_pdf(
    file_path: str,
    metadata: dict[str, object] | None = None,
    settings: Settings | None = None,
) -> ExtractionResult:
    ocr_language = settings.chunking.ocr_language if settings is not None else DEFAULT_CHUNKING.ocr_language
    path_obj = Path(file_path)
    doc_id = str(uuid4())
    doc = fitz.open(file_path)
    blocks: list[StructuredBlock] = []
    images: list[ExtractedImage] = []
    image_ordinal = 0

    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        page_num = page_index + 1
        page_dict = page.get_text("dict")
        raw_blocks = sorted(page_dict.get("blocks", []), key=lambda b: (b.get("bbox", [0, 0])[1], b.get("bbox", [0, 0])[0]))
        page_has_text = False

        for raw in raw_blocks:
            block_type = raw.get("type", 0)
            if block_type == 0:
                lines = []
                for line in raw.get("lines", []):
                    spans = [span.get("text", "") for span in line.get("spans", [])]
                    line_text = "".join(spans).strip()
                    if line_text:
                        lines.append(line_text)
                text = "\n".join(lines).strip()
                if not text:
                    continue
                page_has_text = True
                blocks.append(
                    StructuredBlock(
                        block_id=str(uuid4()),
                        type="paragraph",
                        text=text,
                        page_from=page_num,
                        page_to=page_num,
                    )
                )
                continue

            if block_type == 1:
                xref = raw.get("xref")
                if not xref:
                    continue
                extracted = doc.extract_image(xref)
                image_bytes = extracted.get("image")
                if not image_bytes:
                    continue
                ext = extracted.get("ext", "png")
                mime_type = f"image/{ext.lower()}"
                image_id = str(uuid4())
                anchor = f"[[IMAGE:{image_id}]]"
                images.append(
                    ExtractedImage(
                        image_id=image_id,
                        source_doc_id=doc_id,
                        page=page_num,
                        ordinal=image_ordinal,
                        bytes=image_bytes,
                        mime_type=mime_type,
                        anchor=anchor,
                    )
                )
                blocks.append(
                    StructuredBlock(
                        block_id=str(uuid4()),
                        type="image_anchor",
                        text=anchor,
                        page_from=page_num,
                        page_to=page_num,
                        anchor_image_id=image_id,
                    )
                )
                image_ordinal += 1

        ocr_text = _ocr_page_if_needed(page, text_exists=page_has_text, ocr_language=ocr_language)
        if ocr_text:
            blocks.append(
                StructuredBlock(
                    block_id=str(uuid4()),
                    type="note",
                    text=f"[OCR] {ocr_text}",
                    page_from=page_num,
                    page_to=page_num,
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
