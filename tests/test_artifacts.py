"""Tests for shared local artifact mechanics."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.artifacts import (
    atomic_write_json,
    atomic_write_text,
    canonical_json_hash,
)


class ArtifactUtilityTests(TestCase):
    def test_canonical_hash_ignores_mapping_order(self) -> None:
        self.assertEqual(
            canonical_json_hash({"b": 2, "a": 1}),
            canonical_json_hash({"a": 1, "b": 2}),
        )

    def test_json_write_preserves_pretty_and_compact_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pretty = root / "pretty.json"
            compact = root / "compact.json"

            atomic_write_json(pretty, {"b": 2, "a": 1})
            atomic_write_json(compact, {"b": 2, "a": 1}, indent=None)

            self.assertEqual(
                pretty.read_text(encoding="utf-8"),
                '{\n  "a": 1,\n  "b": 2\n}\n',
            )
            self.assertEqual(compact.read_text(), '{"a": 1, "b": 2}\n')

    def test_text_write_replaces_existing_file_without_temporary_residue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.txt"
            path.write_text("old", encoding="utf-8")

            atomic_write_text(path, "new")

            self.assertEqual(path.read_text(encoding="utf-8"), "new")
            self.assertEqual(tuple(path.parent.glob(f".{path.name}.*")), ())
