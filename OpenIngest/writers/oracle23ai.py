from __future__ import annotations

import json
import logging
import os
from typing import Any

import oracledb

from OpenIngest.config import PipelineConfig
from OpenIngest.models import ChunkRecord
from OpenIngest.writers.base import WriteResult, Writer


logger = logging.getLogger("openingest.writers.oracle23ai")


DEFAULT_TABLE = "RAGTEST1"
LEGACY_TABLE = "RAG_CHUNKS"

COLUMNS: tuple[str, ...] = (
    "RECORD_ID",
    "DOC_ID",
    "SECTION_ID",
    "CHUNK_ID",
    "CHUNK_TYPE",
    "SOURCE_URI",
    "SOURCE_TYPE",
    "PAGE_FROM",
    "PAGE_TO",
    "TITLE",
    "BREADCRUMBS",
    "PITANJE",
    "ODGOVOR",
    "KONTEKST",
    "STEPS_JSON",
    "CONSTRAINTS_JSON",
    "PREREQUISITES_JSON",
    "SYSTEM_EFFECTS_JSON",
    "BRANCHES_JSON",
    "NAVIGATION_PATHS_JSON",
    "CROSS_SYSTEM_REFS_JSON",
    "ERROR_SCENARIOS_JSON",
    "EMPHASIS_SIGNALS_JSON",
    "CUSTOM_FIELDS_JSON",
    "METADATA_JSON",
    "EMBEDDING_MODEL",
    "EMBEDDING_INPUT",
    "APLIKACIJA",
    "EMBEDDING",
)


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


def _as_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


class Oracle23aiWriter(Writer):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def _table_name(self) -> str:
        table_name = (self.config.oracle_table or "").strip()
        if not table_name or table_name.upper() == LEGACY_TABLE:
            return DEFAULT_TABLE
        return table_name

    def _connect(self):
        user = (self.config.oracle_user or os.getenv("ORACLE_USER", "")).strip()
        password = (self.config.oracle_password or os.getenv("ORACLE_PASSWORD", "")).strip()
        dsn = (
            self.config.oracle_dsn
            or os.getenv("ORACLE_DNS", "")
            or os.getenv("ORACLE_DSN", "")
        ).strip()

        if not user or not password or not dsn:
            raise ValueError(
                "Oracle connection cannot be created because ORACLE_USER, ORACLE_PASSWORD, or ORACLE_DNS/ORACLE_DSN is missing."
            )
        try:
            return oracledb.connect(
                user=user,
                password=password,
                dsn=dsn,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to Oracle DSN '{dsn}' as user '{user}' ({type(exc).__name__}: {exc})."
            ) from exc

    def _map_record(self, record: ChunkRecord) -> dict[str, Any]:
        app_from_custom = _get_path(record.text.custom_fields, "app_id")
        app_from_metadata = _get_path(record.metadata, "app_id")
        aplikacija = _to_int_or_none(app_from_custom)
        if aplikacija is None:
            aplikacija = _to_int_or_none(app_from_metadata)

        embedding_payload = _as_json(record.embedding.vector) if record.embedding.vector else None

        return {
            "RECORD_ID": record.record_id,
            "DOC_ID": record.source.doc_id,
            "SECTION_ID": record.unit.parent_id,
            "CHUNK_ID": record.unit.chunk_id,
            "CHUNK_TYPE": record.unit.chunk_type,
            "SOURCE_URI": record.source.uri,
            "SOURCE_TYPE": record.source.type,
            "PAGE_FROM": record.source.page_from,
            "PAGE_TO": record.source.page_to,
            "TITLE": record.text.title,
            "BREADCRUMBS": _as_json(record.text.breadcrumbs),
            "PITANJE": record.text.q,
            "ODGOVOR": record.text.summary,
            "KONTEKST": record.text.content,
            "STEPS_JSON": _as_json(record.text.steps),
            "CONSTRAINTS_JSON": _as_json(record.text.constraints),
            "PREREQUISITES_JSON": _as_json(record.text.prerequisites),
            "SYSTEM_EFFECTS_JSON": _as_json(record.text.system_effects),
            "BRANCHES_JSON": _as_json(record.text.branches),
            "NAVIGATION_PATHS_JSON": _as_json(record.text.navigation_paths),
            "CROSS_SYSTEM_REFS_JSON": _as_json(record.text.cross_system_refs),
            "ERROR_SCENARIOS_JSON": _as_json(record.text.error_scenarios),
            "EMPHASIS_SIGNALS_JSON": _as_json(record.text.emphasis_signals),
            "CUSTOM_FIELDS_JSON": _as_json(record.text.custom_fields),
            "METADATA_JSON": _as_json(record.metadata),
            "EMBEDDING_MODEL": record.embedding.model,
            "EMBEDDING_INPUT": record.embedding.input_text,
            "APLIKACIJA": aplikacija,
            "EMBEDDING": embedding_payload,
        }

    def write(self, records: list[ChunkRecord]) -> WriteResult:
        table_name = self._table_name()
        if not records:
            return WriteResult(destination=table_name)

        bound_records = [self._map_record(record) for record in records]
        bind_sql = ", ".join(
            "CASE WHEN :EMBEDDING IS NULL THEN NULL ELSE TO_VECTOR(:EMBEDDING) END"
            if col == "EMBEDDING"
            else f":{col}"
            for col in COLUMNS
        )
        insert_sql = f"INSERT INTO {table_name} ({', '.join(COLUMNS)}) VALUES ({bind_sql})"

        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    for start in range(0, len(bound_records), self.config.oracle_batch_size):
                        batch = bound_records[start : start + self.config.oracle_batch_size]
                        cursor.executemany(insert_sql, batch)
                conn.commit()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to write {len(bound_records)} records into Oracle table '{table_name}' ({type(exc).__name__}: {exc})."
            ) from exc

        logger.info("Inserted %s records into %s", len(bound_records), table_name)
        return WriteResult(written=len(bound_records), destination=table_name)
