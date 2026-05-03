"""File-backed signal library."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from stock_opportunity_agent.cases.learning import PreSurgeSignalLogic
from stock_opportunity_agent.models import SignalDefinition


@dataclass(frozen=True)
class FileSignalLibrary:
    """Append-friendly local signal library backed by JSON files."""

    root_dir: Path

    def __init__(self, root_dir: str | Path) -> None:
        object.__setattr__(self, "root_dir", Path(root_dir))

    @property
    def definitions_path(self) -> Path:
        """Path to persisted signal definitions."""

        return self.root_dir / "signal_definitions.json"

    @property
    def logic_path(self) -> Path:
        """Path to persisted learned pre-surge logic."""

        return self.root_dir / "pre_surge_signal_logic.json"

    def write_cold_start(
        self,
        *,
        run_id: str,
        definitions: Iterable[SignalDefinition],
        logic: Iterable[PreSurgeSignalLogic],
        created_at: datetime | None = None,
    ) -> None:
        """Persist cold-start signal definitions and learned logic."""

        self.root_dir.mkdir(parents=True, exist_ok=True)
        created = created_at or datetime.now(timezone.utc)
        definition_records = [definition.to_dict() for definition in definitions]
        logic_records = [item.to_dict() for item in logic]
        _write_json(
            self.definitions_path,
            {
                "library": "signal",
                "run_id": run_id,
                "created_at": created.isoformat(),
                "signal_definitions": definition_records,
            },
        )
        _write_json(
            self.logic_path,
            {
                "library": "signal",
                "run_id": run_id,
                "created_at": created.isoformat(),
                "pre_surge_signal_logic": logic_records,
            },
        )

    def read_definitions(self) -> tuple[SignalDefinition, ...]:
        """Read persisted signal definitions."""

        if not self.definitions_path.exists():
            return ()
        data = json.loads(self.definitions_path.read_text(encoding="utf-8"))
        return tuple(SignalDefinition.from_dict(item) for item in data.get("signal_definitions", ()))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
