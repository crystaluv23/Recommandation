"""Incremental JSON reading for existing large local archives."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from stock_opportunity_agent.models import ValidationError


class StreamingJSONReader:
    """Incremental JSON decoder used for multi-hundred-megabyte local archives."""

    def __init__(self, path: Path, *, chunk_size: int = 1024 * 1024,
                 decoder: json.JSONDecoder | None = None, with_hash: bool = False,
                 strict_whitespace: bool = False) -> None:
        self.handle = path.open("r", encoding="utf-8", newline="")
        self.chunk_size = chunk_size
        self.strict_whitespace = strict_whitespace
        self.buffer = ""
        self.position = 0
        self.eof = False
        self.decoder = decoder or json.JSONDecoder()
        self._digest = hashlib.sha256() if with_hash else None

    @property
    def content_sha256(self) -> str:
        """Return the parsed byte-stream hash after complete consumption."""
        if self._digest is None or not self.eof:
            raise ValidationError("stream hash requires complete hashed consumption")
        return self._digest.hexdigest()

    def finish(self) -> None:
        """Require no non-whitespace content after the complete JSON value."""
        self._skip_whitespace()
        if self.position < len(self.buffer):
            raise ValidationError("large price archive has trailing JSON content")

    def close(self) -> None:
        """Close the underlying archive stream."""
        self.handle.close()

    def peek(self) -> str:
        """Return the next non-whitespace character without consuming it."""
        self._skip_whitespace()
        self._ensure_available()
        return self.buffer[self.position]

    def consume(self, expected: str) -> None:
        """Consume one required structural character or reject the archive."""
        actual = self.peek()
        if actual != expected:
            raise ValidationError(
                f"large price archive expected {expected!r}, received {actual!r}"
            )
        self.position += 1
        self._compact()

    def decode(self) -> Any:
        """Decode the next complete JSON value across chunk boundaries."""
        self._skip_whitespace()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
            except json.JSONDecodeError as exc:
                if self.eof:
                    raise ValidationError("large price archive contains invalid JSON") from exc
                self._fill()
                continue
            if end == len(self.buffer) and not self.eof:
                self._fill()
                continue
            self.position = end
            self._compact()
            return value

    def _skip_whitespace(self) -> None:
        while True:
            while self.position < len(self.buffer) and (self.buffer[self.position] in " \t\r\n" if self.strict_whitespace
                 else self.buffer[self.position].isspace()):
                self.position += 1
            if self.position < len(self.buffer) or self.eof:
                return
            self._fill()

    def _ensure_available(self) -> None:
        if self.position >= len(self.buffer) and not self.eof:
            self._fill()
        if self.position >= len(self.buffer):
            raise ValidationError("large price archive ended unexpectedly")

    def _fill(self) -> None:
        chunk = self.handle.read(self.chunk_size)
        if self._digest is not None:
            self._digest.update(chunk.encode("utf-8"))
        if not chunk:
            self.eof = True
            return
        if self.position:
            self.buffer = self.buffer[self.position :] + chunk
            self.position = 0
        else:
            self.buffer += chunk

    def _compact(self) -> None:
        if self.position > self.chunk_size:
            self.buffer = self.buffer[self.position :]
            self.position = 0
