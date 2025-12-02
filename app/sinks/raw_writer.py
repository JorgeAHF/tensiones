"""Utilities for writing raw streaming data to disk immediately."""

from __future__ import annotations

import csv
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Tuple


class RawStreamingWriter:
    """Persist raw accelerometer samples directly from the streaming thread."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        self._header_written: set[Path] = set()
        self._header_lock = threading.Lock()

    def append_batch(
        self,
        sensor_id: str,
        samples: Iterable[Tuple[float, float, float, float]],
    ) -> None:
        """Append a batch of samples to disk, grouping them per day."""

        grouped: defaultdict[Path, List[Tuple[float, float, float, float]]] = defaultdict(list)
        for timestamp, x, y, z in samples:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            filename = dt.strftime("%Y%m%d")
            file_path = self._base_dir / sensor_id / f"{filename}.csv"
            grouped[file_path].append((timestamp, x, y, z))

        for file_path, rows in grouped.items():
            if not rows:
                continue
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with self._locks[file_path.as_posix()]:
                self._ensure_header(file_path)
                with file_path.open("a", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerows(rows)

    def _ensure_header(self, file_path: Path) -> None:
        with self._header_lock:
            if file_path in self._header_written:
                return

            if not file_path.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with file_path.open("w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["timestamp_epoch", "x_g", "y_g", "z_g"])

            self._header_written.add(file_path)


__all__ = ["RawStreamingWriter"]
