from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from OpenIngest.models import ChunkRecord
from OpenIngest.writers.base import WriteResult, Writer


class JsonlWriter(Writer):
    def __init__(self, output_path: str, cleanprint: bool = False) -> None:
        self.output_path = Path(output_path)
        self.cleanprint = cleanprint

    def _prepare_record(self, record: ChunkRecord) -> dict:
        data = asdict(record)
        if self.cleanprint:
            embedding = data.get("embedding")
            if isinstance(embedding, dict):
                embedding.pop("vector", None)
        return data

    def write(self, records: list[ChunkRecord]) -> WriteResult:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            for record in records:
                payload = self._prepare_record(record)
                if self.cleanprint:
                    handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                else:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return WriteResult(written=len(records), destination=str(self.output_path))
