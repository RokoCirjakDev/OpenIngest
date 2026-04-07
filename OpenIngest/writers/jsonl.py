from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from OpenIngest.models import ChunkRecord
from OpenIngest.writers.base import WriteResult, Writer


class JsonlWriter(Writer):
    def __init__(self, output_path: str) -> None:
        self.output_path = Path(output_path)

    def write(self, records: list[ChunkRecord]) -> WriteResult:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return WriteResult(written=len(records), destination=str(self.output_path))
