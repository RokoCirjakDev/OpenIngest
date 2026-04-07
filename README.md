# OpenIngest

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](./pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](./OpenIngest/serve.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

OpenIngest builds **in-depth AI/RAG knowledge datasets** from average, messy documentation.

It converts DOCX/PDF files into structured records that include source context, hierarchy, generated Q/A, embeddings, and traceability fields—so the output is retrieval-ready, not just raw text.

## Table of Contents

- [Why OpenIngest](#why-openingest)
- [Workflow](#workflow)
- [Extreme Configurability](#extreme-configurability)
- [Output Architecture (Oracle is an Example)](#output-architecture-oracle-is-an-example)
- [Create a Custom Writer in 5 Minutes](#create-a-custom-writer-in-5-minutes)
- [Quick Start](#quick-start)

## Why OpenIngest

Real documentation is usually not RAG-ready:

- inconsistent structure
- long procedural blocks
- critical meaning hidden in screenshots
- mixed tables, notes, steps, and troubleshooting

OpenIngest transforms that into structured knowledge with:

- `KONTEKST` (grounded chunk text)
- `PITANJE` / `ODGOVOR` (retrieval-friendly intent + concise answer)
- breadcrumbs + page ranges
- embeddings + model provenance
- stable IDs (`DOC_ID`, `SECTION_ID`, `CHUNK_ID`)

## Workflow

1. Extract blocks from DOCX/PDF
2. Extract images and optionally caption with vision
3. Merge image descriptions inline
4. Compute heading breadcrumbs
5. Detect parent sections
6. Split into child chunks (token/overlap aware)
7. Generate questions/summaries/keywords
8. Embed chunks
9. Write records via selected writer

## Extreme Configurability

OpenIngest is intentionally configurable at every stage.

- **Config sources**: defaults, JSON/YAML config file, environment variables
- **Chunking**: mode (`procedure`/`structure`/`window`/`semantic`), token targets, overlap, heading/keyword heuristics, OCR language
- **Enrichment**: language strategy, image captions, summaries, synthetic questions, prompts
- **Embedding**: model, dimensions, batch size, input template
- **Pipeline control**: per-stage enablement (`extract`, `chunk`, `enrich_text`, `embed`, `write`, etc.)
- **Writer mapping**: destination field mapping is configurable via `writer.mapping`

This means the same core pipeline can be adapted to very different documentation styles, data contracts, and storage backends.

## Output Architecture (Oracle is an Example)

OpenIngest output is **writer-driven**.

- Current built-ins: `jsonl`, `oracle23ai`
- The Oracle writer in this repo reflects a **specific schema used by one application at my current firm**
- It is provided as a **reference implementation**, not a platform limitation

You can target alternative database architectures by adding another writer implementation (same `Writer` interface) and selecting it through `writer.kind`.

In other words: Oracle is one adapter example; the architecture is extensible by design.

## Create a Custom Writer in 5 Minutes

1. Create a new file in `OpenIngest/writers/`, for example `mydb_writer.py`.
2. Implement the `Writer` interface from `OpenIngest.writers.base`.
3. Convert each `ChunkRecord` into your DB/API payload.
4. Return a `WriteResult` with counts and destination.
5. Register/select your writer via `writer.kind` in config.

Minimal example:

```python
from OpenIngest.writers.base import Writer, WriteResult
from OpenIngest.models import ChunkRecord


class MyDbWriter(Writer):
		def write(self, records: list[ChunkRecord]) -> WriteResult:
				# map records -> your storage schema, then insert
				inserted = len(records)
				return WriteResult(written=inserted, destination="mydb")
```

Config example:

```yaml
writer:
	kind: mydb
```

Tip: start by copying `OpenIngest/writers/oracle23ai.py` or `OpenIngest/writers/jsonl.py` and replacing only the mapping + write logic.

## Quick Start

### Backend

```bash
pip install -e .
uvicorn OpenIngest.serve:app --reload
```

### UI

```bash
cd ui
npm install
npm run dev
```

### CLI

```bash
openingest-ingest /path/to/file.pdf --metadata "{\"app_id\":\"10\"}"
```

Accepted sources: `.pdf`, `.docx`.

### Common environment variables

```bash
OPENAI_API_KEY=...
ORACLE_USER=...
ORACLE_PASSWORD=...
ORACLE_DSN=host/service_name

OPENINGEST_VISION_MODEL=gpt-4.1-mini
OPENINGEST_SUMMARIZE_MODEL=gpt-4.1-mini
OPENINGEST_EMBEDDING_MODEL=text-embedding-3-small
OPENINGEST_VISION_MAX_WORKERS=4
OPENINGEST_OPENAI_MAX_RETRIES=4
OPENINGEST_OPENAI_BACKOFF=1.0
ORACLE_TABLE=RAG_CHUNKS
ORACLE_BATCH_SIZE=50
```
