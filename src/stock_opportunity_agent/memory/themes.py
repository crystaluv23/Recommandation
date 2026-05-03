"""File-backed theme map library."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from stock_opportunity_agent.models import ThemeMap


@dataclass(frozen=True)
class FileThemeLibrary:
    """Local JSON-backed store for cold-start theme maps."""

    root_dir: Path

    def __init__(self, root_dir: str | Path) -> None:
        object.__setattr__(self, "root_dir", Path(root_dir))

    @property
    def theme_maps_path(self) -> Path:
        """Path to persisted theme maps."""

        return self.root_dir / "theme_maps.json"

    def write_cold_start(
        self,
        *,
        run_id: str,
        theme_maps: Iterable[ThemeMap],
        created_at: datetime | None = None,
    ) -> None:
        """Persist cold-start theme maps."""

        self.root_dir.mkdir(parents=True, exist_ok=True)
        created = created_at or datetime.now(timezone.utc)
        _write_json(
            self.theme_maps_path,
            {
                "library": "theme",
                "run_id": run_id,
                "created_at": created.isoformat(),
                "theme_maps": [theme.to_dict() for theme in theme_maps],
            },
        )

    def read_theme_maps(self) -> tuple[ThemeMap, ...]:
        """Read persisted theme maps."""

        if not self.theme_maps_path.exists():
            return ()
        data = json.loads(self.theme_maps_path.read_text(encoding="utf-8"))
        return tuple(ThemeMap.from_dict(item) for item in data.get("theme_maps", ()))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
