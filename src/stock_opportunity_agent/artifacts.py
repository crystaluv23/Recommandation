"""Canonical hashing and crash-safe writes for local artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TextIO


def canonical_json_hash(value: Any) -> str:
    """Return a deterministic SHA-256 hash for one JSON-compatible value."""

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_json(
    path: Path,
    value: Mapping[str, Any],
    *,
    indent: int | None = 2,
) -> None:
    """Atomically replace ``path`` with one deterministic JSON object."""

    def write(handle: TextIO) -> None:
        json.dump(value, handle, sort_keys=True, indent=indent)
        handle.write("\n")

    _atomic_write(path, write)


def atomic_write_text(path: Path, value: str) -> None:
    """Atomically replace ``path`` with already serialized UTF-8 text."""

    _atomic_write(path, lambda handle: handle.write(value))


def _atomic_write(path: Path, write: Callable[[TextIO], object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
