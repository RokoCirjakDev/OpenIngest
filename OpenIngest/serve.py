from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from typing import Any

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
) -> dict[str, Any]:
    return {
        "status": "received",
        "filename": file.filename,
        "extra_instructions": extra_instructions,
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
