from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal

from OpenIngest.defaults import DEFAULT_CHUNKING, DEFAULT_EMBEDDING, DEFAULT_ENRICHMENT, DEFAULT_WRITER

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


@dataclass(slots=True)
class PromptConfig:
    image_caption: str = DEFAULT_ENRICHMENT.prompt.image_caption
    summarize: str = DEFAULT_ENRICHMENT.prompt.summarize
    synthetic_questions: str = DEFAULT_ENRICHMENT.prompt.synthetic_questions


@dataclass(slots=True)
class EnrichmentConfig:
    language: str = DEFAULT_ENRICHMENT.language
    image_caption_enabled: bool = True
    summarize_enabled: bool = True
    generate_queries_enabled: bool = False
    keywords_enabled: bool = True
    generate_queries_count: int = 1
    prompt: PromptConfig = field(default_factory=PromptConfig)


@dataclass(slots=True)
class ChunkingConfig:
    mode: Literal["procedure", "structure", "window", "semantic"] = DEFAULT_CHUNKING.mode
    target_tokens: int = DEFAULT_CHUNKING.target_tokens
    min_tokens: int = DEFAULT_CHUNKING.min_tokens
    hard_cap_tokens: int = DEFAULT_CHUNKING.hard_cap_tokens
    overlap_tokens: int = DEFAULT_CHUNKING.overlap_tokens
    overlap_steps: int = DEFAULT_CHUNKING.overlap_steps
    split_by_headings: bool = DEFAULT_CHUNKING.split_by_headings
    split_by_semantics: bool = DEFAULT_CHUNKING.split_by_semantics
    task_heading_prefixes: tuple[str, ...] = DEFAULT_CHUNKING.task_heading_prefixes
    prereq_keywords: tuple[str, ...] = DEFAULT_CHUNKING.prereq_keywords
    troubleshooting_keywords: tuple[str, ...] = DEFAULT_CHUNKING.troubleshooting_keywords
    example_keywords: tuple[str, ...] = DEFAULT_CHUNKING.example_keywords
    ocr_language: str = DEFAULT_CHUNKING.ocr_language


@dataclass(slots=True)
class EmbeddingConfig:
    model: str = DEFAULT_EMBEDDING.model
    batch_size: int = DEFAULT_EMBEDDING.batch_size
    dimensions: int | None = DEFAULT_EMBEDDING.dimensions
    input_template: str = DEFAULT_EMBEDDING.input_template


@dataclass(slots=True)
class WriterConfig:
    kind: str = DEFAULT_WRITER.kind
    required_metadata_keys: list[str] = field(default_factory=list)
    mapping: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_WRITER.mapping))


@dataclass(slots=True)
class PipelineConfig:
    language: str = "auto"
    version: str = "1"
    config_path: str | None = None
    openai_api_key: str = ""
    vision_model: str = "gpt-4.1-mini"
    summarize_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    vision_max_workers: int = 4
    openai_max_retries: int = 4
    openai_initial_backoff_seconds: float = 1.0
    image_cache_path: str = ".openingest_image_cache.json"
    state_cache_path: str = ".openingest_doc_state.json"
    oracle_user: str = ""
    oracle_password: str = ""
    oracle_dsn: str = ""
    oracle_table: str = "RAG_CHUNKS"
    oracle_batch_size: int = 50
    chunk_target_tokens: int = 450
    chunk_min_tokens: int = 300
    chunk_hard_cap_tokens: int = 600
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    writer: WriterConfig = field(default_factory=WriterConfig)
    metadata_defaults: dict[str, Any] = field(default_factory=dict)
    stage_enablement: dict[str, bool] = field(
        default_factory=lambda: {
            "extract": True,
            "image_caption": True,
            "inline_merge": True,
            "chunk": True,
            "enrich_text": True,
            "embed": True,
            "write": True,
        }
    )


Settings = PipelineConfig


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
    return target


def _asdict_dataclass(obj: Any) -> dict[str, Any]:
    if not is_dataclass(obj):
        return obj
    return {f.name: _asdict_dataclass(getattr(obj, f.name)) for f in fields(obj)}


def _build_config(data: dict[str, Any]) -> PipelineConfig:
    enrichment = data.pop("enrichment", {}) or {}
    enrichment_prompt = enrichment.pop("prompt", {}) or {}
    chunking = data.pop("chunking", {}) or {}
    embedding = data.pop("embedding", {}) or {}
    writer = data.pop("writer", {}) or {}
    config = PipelineConfig(**data)
    config.enrichment = EnrichmentConfig(
        **enrichment,
        prompt=PromptConfig(**enrichment_prompt),
    )
    config.chunking = ChunkingConfig(**chunking)
    config.embedding = EmbeddingConfig(**embedding)
    config.writer = WriterConfig(**writer)
    return config


def _env_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def load_config(config_path: str | None = None) -> PipelineConfig:
    path = config_path or os.getenv("OPENINGEST_CONFIG_PATH")
    base = _asdict_dataclass(PipelineConfig())

    if path:
        file_path = Path(path)
        if file_path.exists():
            if file_path.suffix.lower() in {".yml", ".yaml"}:
                if yaml is None:
                    raise ImportError("PyYAML is required to load YAML configs")
                loaded = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
            else:
                loaded = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                _deep_update(base, loaded)
            base["config_path"] = str(file_path)

    env_overrides = {
        "openai_api_key": os.getenv("OPENAI_API_KEY", base.get("openai_api_key", "")),
        "vision_model": os.getenv("OPENINGEST_VISION_MODEL", base.get("vision_model", "gpt-4.1-mini")),
        "summarize_model": os.getenv("OPENINGEST_SUMMARIZE_MODEL", base.get("summarize_model", "gpt-4.1-mini")),
        "embedding_model": os.getenv("OPENINGEST_EMBEDDING_MODEL", base.get("embedding_model", "text-embedding-3-small")),
        "vision_max_workers": int(os.getenv("OPENINGEST_VISION_MAX_WORKERS", str(base.get("vision_max_workers", 4)))),
        "openai_max_retries": int(os.getenv("OPENINGEST_OPENAI_MAX_RETRIES", str(base.get("openai_max_retries", 4)))),
        "openai_initial_backoff_seconds": float(os.getenv("OPENINGEST_OPENAI_BACKOFF", str(base.get("openai_initial_backoff_seconds", 1.0)))),
        "image_cache_path": os.getenv("OPENINGEST_IMAGE_CACHE_PATH", base.get("image_cache_path", ".openingest_image_cache.json")),
        "state_cache_path": os.getenv("OPENINGEST_STATE_CACHE_PATH", base.get("state_cache_path", ".openingest_doc_state.json")),
        "oracle_user": os.getenv("ORACLE_USER", base.get("oracle_user", "")),
        "oracle_password": os.getenv("ORACLE_PASSWORD", base.get("oracle_password", "")),
        "oracle_dsn": os.getenv("ORACLE_DSN", base.get("oracle_dsn", "")),
        "oracle_table": os.getenv("ORACLE_TABLE", base.get("oracle_table", "RAG_CHUNKS")),
        "oracle_batch_size": int(os.getenv("ORACLE_BATCH_SIZE", str(base.get("oracle_batch_size", 50)))),
        "chunk_target_tokens": int(os.getenv("OPENINGEST_CHUNK_TARGET_TOKENS", str(base.get("chunk_target_tokens", 450)))),
        "chunk_min_tokens": int(os.getenv("OPENINGEST_CHUNK_MIN_TOKENS", str(base.get("chunk_min_tokens", 300)))),
        "chunk_hard_cap_tokens": int(os.getenv("OPENINGEST_CHUNK_HARD_CAP_TOKENS", str(base.get("chunk_hard_cap_tokens", 600)))),
    }
    base["chunking"]["task_heading_prefixes"] = _env_tuple("OPENINGEST_TASK_HEADING_PREFIXES", tuple(base["chunking"].get("task_heading_prefixes", ())))
    base["chunking"]["prereq_keywords"] = _env_tuple("OPENINGEST_PREREQ_KEYWORDS", tuple(base["chunking"].get("prereq_keywords", ())))
    base["chunking"]["troubleshooting_keywords"] = _env_tuple("OPENINGEST_TROUBLESHOOTING_KEYWORDS", tuple(base["chunking"].get("troubleshooting_keywords", ())))
    base["chunking"]["example_keywords"] = _env_tuple("OPENINGEST_EXAMPLE_KEYWORDS", tuple(base["chunking"].get("example_keywords", ())))
    _deep_update(base, env_overrides)
    return _build_config(base)


def load_settings(config_path: str | None = None) -> PipelineConfig:
    return load_config(config_path)
