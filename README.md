# OpenIngest

Minimal React UI + FastAPI stub server for document and manual text ingestion.

## Repo structure

```
/
  ui/           # React app (Vite + shadcn/ui)
  OpenIngest/   # Python package
    serve.py    # FastAPI stub server
  pyproject.toml
  README.md
```

## Backend (FastAPI)

### Install

```bash
pip install fastapi "uvicorn[standard]" python-multipart
```

### Run

```bash
uvicorn OpenIngest.serve:app --reload
```

Server starts at **http://localhost:8000**.

#### Endpoints

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/upload/doc` | `multipart/form-data` — `file` + optional `extra_instructions` | `{"status":"received","filename":…,"extra_instructions":…}` |
| POST | `/upload/manual` | JSON — `{"text":…,"metadata":{…}}` | `{"status":"received","text_length":…,"metadata_keys":[…]}` |

Interactive docs: http://localhost:8000/docs

## UI (React + Vite)

### Install

```bash
cd ui
npm install
```

### Run

```bash
npm run dev
```

App opens at **http://localhost:5173**.

The UI expects the backend running at `http://localhost:8000`. Change `API_BASE` in `ui/src/App.tsx` to use a different address.

### Tabs

- **Doc ingest** — pick a file, optionally expand *Advanced* to add extra instructions, then click *Upload*. POSTs `multipart/form-data` to `/upload/doc`.
- **Manual ingest** — enter text, add key/value metadata rows with the *+* button, then click *Submit*. POSTs JSON to `/upload/manual`.

Both tabs display the JSON response (or an error message) below the submit button.
