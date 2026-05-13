"""File-backed research playbook library."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from stock_opportunity_agent.research.playbooks import SurgePlaybookSynthesis, SurgeResearchPlaybook


@dataclass(frozen=True)
class FilePlaybookLibrary:
    """Local JSON-backed store for cold-start research playbooks."""

    root_dir: Path

    def __init__(self, root_dir: str | Path) -> None:
        object.__setattr__(self, "root_dir", Path(root_dir))

    @property
    def playbooks_path(self) -> Path:
        """Path to persisted research playbooks."""

        return self.root_dir / "surge_research_playbooks.json"

    def write_cold_start(
        self,
        *,
        run_id: str,
        synthesis: SurgePlaybookSynthesis,
        created_at: datetime | None = None,
    ) -> None:
        """Persist cold-start research playbooks."""

        self.root_dir.mkdir(parents=True, exist_ok=True)
        created = created_at or datetime.now(timezone.utc)
        _write_json(
            self.playbooks_path,
            {
                "library": "playbook",
                "run_id": run_id,
                "created_at": created.isoformat(),
                **synthesis.to_dict(),
            },
        )

    def read_playbooks(self) -> tuple[SurgeResearchPlaybook, ...]:
        """Read persisted research playbooks."""

        if not self.playbooks_path.exists():
            return ()
        data = json.loads(self.playbooks_path.read_text(encoding="utf-8"))
        return tuple(SurgeResearchPlaybook.from_dict(item) for item in data.get("playbooks", ()))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
