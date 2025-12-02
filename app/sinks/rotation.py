"""File rotation utilities for CSV storage."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


@dataclass
class RotationPolicy:
    mode: str
    minutes: Optional[int] = None
    max_mb: Optional[int] = None

    def should_rotate(
        self,
        path: Path,
        created_at: datetime,
        now: Optional[datetime] = None,
    ) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.mode == "time" and self.minutes is not None:
            return now - created_at >= timedelta(minutes=self.minutes)
        if self.mode == "size" and self.max_mb is not None:
            size_mb = path.stat().st_size / (1024 * 1024) if path.exists() else 0
            return size_mb >= self.max_mb
        return False


class RotatingFile:
    """Handle time or size based rotation for CSV files."""

    def __init__(self, base_dir: Path, prefix: str, policy: RotationPolicy) -> None:
        self.base_dir = base_dir
        self.prefix = prefix
        self.policy = policy
        self._current_path: Optional[Path] = None
        self._created_at: Optional[datetime] = None
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _next_path(self) -> Path:
        # Usar hora CST (Central Standard Time - México)
        cst_tz = ZoneInfo("America/Mexico_City")
        now_cst = datetime.now(cst_tz)
        timestamp = now_cst.strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{self.prefix}_{timestamp}.csv"
        return self.base_dir / filename

    def _open_new(self) -> Path:
        self._current_path = self._next_path()
        # Usar UTC internamente para comparaciones de rotación
        self._created_at = datetime.now(timezone.utc)
        return self._current_path

    def path(self) -> Path:
        if self._current_path is None:
            return self._open_new()
        if self.policy.should_rotate(self._current_path, self._created_at or datetime.now(timezone.utc)):
            return self._open_new()
        return self._current_path


__all__ = ["RotationPolicy", "RotatingFile"]
