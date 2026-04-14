from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

import oracledb

from OpenIngest.config import PipelineConfig
from OpenIngest.models import ChunkRecord
from OpenIngest.writers.base import WriteResult, Writer


logger = logging.getLogger("openingest.writers.oracle23ai")


def _get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


class Oracle23aiWriter(Writer):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def _connect(self):
        if not self.config.oracle_user or not self.config.oracle_password or not self.config.oracle_dsn:
            raise ValueError(
                "Oracle connection cannot be created because ORACLE_USER, ORACLE_PASSWORD, or ORACLE_DSN is missing from the active configuration."
            )
        try:
            return oracledb.connect(
                user=self.config.oracle_user,
                password=self.config.oracle_password,
                dsn=self.config.oracle_dsn,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to Oracle DSN '{self.config.oracle_dsn}' as user '{self.config.oracle_user}' ({type(exc).__name__}: {exc})."
            ) from exc

    def _map_record(self, record: ChunkRecord) -> dict[str, Any]:
        base = asdict(record)
        bound: dict[str, Any] = {}
        mapping = self.config.writer.mapping or {
            "PITANJE": "text.q",
            "ODGOVOR": "text.summary",
            "KONTEKST": "text.content",
            "APP_ID": "metadata.app_id",
            "EMBEDDING": "embedding.vector",
        }
        for destination, source in mapping.items():
            value = _get_path(base, source) if isinstance(source, str) else source
            if destination == "EMBEDDING" and isinstance(value, list):
                value = json.dumps(value)
            bound[destination] = value
        return bound

    def write(self, records: list[ChunkRecord]) -> WriteResult:
        if not records:
            return WriteResult(destination="oracle23ai")

        bound_records = [self._map_record(record) for record in records]
        columns = list(bound_records[0].keys())
        bind_sql = ", ".join("TO_VECTOR(:EMBEDDING)" if col == "EMBEDDING" else f":{col}" for col in columns)
        insert_sql = f"INSERT INTO {self.config.oracle_table} ({', '.join(columns)}) VALUES ({bind_sql})"

        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    for start in range(0, len(bound_records), self.config.oracle_batch_size):
                        batch = bound_records[start : start + self.config.oracle_batch_size]
                        cursor.executemany(insert_sql, batch)
                conn.commit()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to write {len(bound_records)} records into Oracle table '{self.config.oracle_table}' ({type(exc).__name__}: {exc})."
            ) from exc

        logger.info("Inserted %s records into %s", len(bound_records), self.config.oracle_table)
        return WriteResult(written=len(bound_records), destination="oracle23ai")
