from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, TypeVar


logger = logging.getLogger("openingest")
T = TypeVar("T")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str | Path) -> str:
    path_obj = Path(path)
    digest = hashlib.sha256()
    with path_obj.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def retry_with_backoff(
    func: Callable[[], T],
    *,
    max_retries: int,
    initial_backoff_seconds: float,
    retry_exceptions: tuple[type[Exception], ...],
) -> T:
    attempt = 0
    backoff = initial_backoff_seconds
    while True:
        try:
            return func()
        except retry_exceptions as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            logger.warning("Retrying after error (%s/%s): %s", attempt, max_retries, exc)
            time.sleep(backoff)
            backoff *= 2


class JsonStateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value

    def flush(self) -> None:
        self.path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
