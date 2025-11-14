"""CSV writing utilities with rotation support."""
from __future__ import annotations

import csv
from pathlib import Path
from threading import Lock
from typing import Iterable, List, Sequence

from app.sinks.rotation import RotatingFile, RotationPolicy


class RotatingCsvWriter:
    """Thread-safe CSV writer that rotates files based on a policy."""

    def __init__(
        self,
        base_dir: Path,
        prefix: str,
        headers: Sequence[str],
        policy: RotationPolicy,
    ) -> None:
        self._rotator = RotatingFile(base_dir, prefix, policy)
        self._headers = list(headers)
        self._lock = Lock()

    def _ensure_header(self, path: Path) -> None:
        if path.exists() and path.stat().st_size > 0:
            return
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self._headers)

    def writerow(self, row: Sequence) -> Path:
        with self._lock:
            path = self._rotator.path()
            self._ensure_header(path)
            with path.open("a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(row)
            return path

    def writerows(self, rows: Iterable[Sequence]) -> Path:
        """Write multiple rows efficiently - only check rotation once."""
        with self._lock:
            path = self._rotator.path()  # Check rotation ONCE
            self._ensure_header(path)
            with path.open("a", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)  # Write all rows at once
            return path

    @property
    def current_path(self) -> Path:
        """Get the current file path (without triggering rotation)."""
        with self._lock:
            return self._rotator._current_path or self._rotator.path()


__all__ = ["RotatingCsvWriter"]
