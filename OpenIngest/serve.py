from pathlib import Path
from tempfile import NamedTemporaryFile
import json
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from OpenIngest.orchestrator import run_pipeline

app = FastAPI(title="OpenIngest")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload/doc")
async def upload_doc(
    file: UploadFile = File(...),
    extra_instructions: str = Form(""),
    metadata: str = Form("{}"),
    config_path: str | None = Form(None),
) -> dict[str, Any]:
    suffix = Path(file.filename or "uploaded").suffix or ".bin"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(await file.read())
        temp_path = temp_file.name

    try:
        metadata_obj = json.loads(metadata) if metadata else {}
        if not isinstance(metadata_obj, dict):
            raise HTTPException(
                status_code=400,
                detail="Invalid metadata payload: expected a JSON object at form field 'metadata'.",
            )
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metadata payload: failed to parse JSON in form field 'metadata' ({type(exc).__name__}: {exc}).",
        ) from exc
    if extra_instructions:
        metadata_obj.setdefault("extra_instructions", extra_instructions)

    try:
        stats = await run_in_threadpool(run_pipeline, temp_path, metadata_obj, config_path)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed for uploaded file '{file.filename or 'uploaded'}' ({type(exc).__name__}: {exc}).",
        ) from exc
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except OSError:
            pass

    return {
        "status": "processed",
        "filename": file.filename,
        "extra_instructions": extra_instructions,
        "metadata": metadata_obj,
        "config_path": config_path,
        "stats": {
            "source_uri": stats.source_uri,
            "doc_id": stats.doc_id,
            "images_total": stats.images_total,
            "parents_total": stats.parents_total,
            "children_total": stats.children_total,
            "uploaded_rows": stats.uploaded_rows,
            "skipped_as_unchanged": stats.skipped_as_unchanged,
        },
    }


@app.post("/upload/manual")
async def upload_manual(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "received",
        "text_length": len(payload.get("text", "")),
        "metadata_keys": list(payload.get("metadata", {}).keys()),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("OpenIngest.serve:app", host="0.0.0.0", port=8000, reload=True)
