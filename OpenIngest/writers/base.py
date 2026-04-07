from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from OpenIngest.models import ChunkRecord


@dataclass(slots=True)
class WriteResult:
    written: int = 0
    skipped: int = 0
    destination: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class Writer(ABC):
    @abstractmethod
    def write(self, records: list[ChunkRecord]) -> WriteResult:
        raise NotImplementedError
