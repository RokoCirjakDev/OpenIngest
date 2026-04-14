from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class PromptDefaults:
    image_caption: str = "Describe the image in the document in the same language as the source document."
    summarize: str = (
        "Generate a knowledgeable explanation in 2-4 sentences that directly answers the user's intent, "
        "without listing explicit numbered steps inside the summary. "
        "If the chunk is informational and contains no actionable sequence, keep the steps array empty."
    )
    synthetic_questions: str = "Create a search-friendly question that matches the intent of the section."


@dataclass(slots=True)
class EnrichmentDefaults:
    language: str = "auto"
    prompt: PromptDefaults = field(default_factory=PromptDefaults)
    custom_fields: list[dict[str, object]] = field(
        default_factory=lambda: [
            {
                "name": "app_id",
                "type": "enum",
                "description": [
                    "Classify the application identifier used by this chunk, if its a multi app workflow, clasify it as the one in which it begins in.",
                    "Aplikacija Likvidatura (ID=12) prvenstveno služi za upravljanje ulaznim računima (URA), što uključuje postupke storniranja neplaćenih i plaćenih računa te preknjiženja računa za korisnike izvan sustava riznice. Kroz ovaj modul korisnici rješavaju neravnoteže između iznosa računa i virmana kod povrata te mogu mijenjati pozicije na originalnom računu za potrebe ispravaka",
                    "Aplikacija Nalozi (ID=31) omogućava otvaranje i provedbu platnih naloga koji su podijeljeni u tri glavne vrste: obračuni, ulazni računi (URA) i preknjižbe. Unutar modula korisnici mogu dodavati ili izbacivati račune iz naloga, prenositi podatke o isplatama u knjigu te vršiti složena preknjiženja, poput povezivanja i zatvaranja isplaćenog predujma s odgovarajućom urom.",
                    "Aplikacija Financije (ID=16) predstavlja sustav glavne knjige u kojem se obrađuju izvodi, provode povrati dobavljača na temeljnici izvoda te ispravljaju greške u analitici. Aplikacija nudi napredne alate za manipulaciju prihodima s izvoda, uključujući podjelu jedne uplate na dva različita prihoda, promjene prihoda s ostavljanjem traga transakcije ili bez njega te rješavanje uplata koje ne trebaju proći analitiku."
                    #"Random aplikacija koje nema u ovom dokumentu",
                    "Return exactly one of the configured enum values.",
                ],
                "required": True,
                "options": ["12", "31", "16"],
            }
        ]
    )


@dataclass(slots=True)
class ChunkingDefaults:
    mode: Literal["procedure", "structure", "window", "semantic"] = "procedure"
    target_tokens: int = 450
    min_tokens: int = 300
    hard_cap_tokens: int = 600
    overlap_tokens: int = 80
    overlap_steps: int = 1
    split_by_headings: bool = True
    split_by_semantics: bool = False
    task_heading_prefixes: tuple[str, ...] = (
        "kako",
        "postupak",
        "konfiguracija",
        "upute",
        "rješavanje problema",
        "rad sa",
        "postavljanje",
        "izvoz",
        "uvoz",
    )
    prereq_keywords: tuple[str, ...] = ("preduvjet", "prije nego", "uloga", "dozvola")
    troubleshooting_keywords: tuple[str, ...] = ("pogreška", "rješenje", "greška", "error", "ako ")
    example_keywords: tuple[str, ...] = ("primjer", "npr.", "example", "```", "kod")
    ocr_language: str = "hrv+eng"


@dataclass(slots=True)
class EmbeddingDefaults:
    model: str = "text-embedding-3-small"
    batch_size: int = 32
    dimensions: int | None = None
    input_template: str = "{title}\n{breadcrumbs}\n\n{content}"


@dataclass(slots=True)
class WriterDefaults:
    kind: str = "jsonl"
    cleanprint: bool = True
    required_metadata_keys: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=lambda: {
        "PITANJE": "text.q",
        "ODGOVOR": "text.summary",
        "KONTEKST": "text.content",
        "APP_ID": "metadata.app_id",
        "EMBEDDING": "embedding.vector",
        "DOC_ID": "source.doc_id",
        "SECTION_ID": "unit.parent_id",
        "CHUNK_ID": "unit.chunk_id",
        "CHUNK_TYPE": "unit.chunk_type",
        "SOURCE_URI": "source.uri",
        "PAGE_FROM": "source.page_from",
        "PAGE_TO": "source.page_to",
        "BREADCRUMBS": "text.breadcrumbs",
        "EMBEDDING_MODEL": "embedding.model",
        "EMBEDDING_INPUT": "embedding.input_text",
    })


DEFAULT_PROMPTS = PromptDefaults()
DEFAULT_ENRICHMENT = EnrichmentDefaults()
DEFAULT_CHUNKING = ChunkingDefaults()
DEFAULT_EMBEDDING = EmbeddingDefaults()
DEFAULT_WRITER = WriterDefaults()
