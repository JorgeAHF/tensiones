"""Parquet writing utilities with rotation support."""
from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Iterable, Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.sinks.rotation import RotatingFile, RotationPolicy


class RotatingParquetWriter:
    """Thread-safe Parquet writer that rotates files based on a policy.

    Advantages over CSV:
    - 5-10x smaller file sizes with compression
    - 10-50x faster reads for analysis
    - Type safety (no string parsing)
    - Built-in compression (snappy)
    """

    def __init__(
        self,
        base_dir: Path,
        prefix: str,
        headers: Sequence[str],
        policy: RotationPolicy,
        compression: str = "snappy",
    ) -> None:
        # Modify rotator to use .parquet extension
        self._rotator = RotatingFile(base_dir, prefix, policy)
        self._headers = list(headers)
        self._lock = Lock()
        self._compression = compression

        # Define schema based on headers
        # Assume: timestamp_utc, timestamp_local are timestamps
        # acceleration_g is float64
        # sensor_id is string
        self._schema = self._infer_schema(headers)

    def _infer_schema(self, headers: Sequence[str]) -> pa.Schema:
        """Infer PyArrow schema from header names."""
        fields = []
        for header in headers:
            if "timestamp" in header:
                fields.append(pa.field(header, pa.timestamp("ms")))
            elif header == "sensor_id":
                fields.append(pa.field(header, pa.string()))
            elif "acceleration" in header or header in ["x", "y", "z"]:
                fields.append(pa.field(header, pa.float64()))
            else:
                # Default to string
                fields.append(pa.field(header, pa.string()))
        return pa.schema(fields)

    def _get_path(self) -> Path:
        """Get current path with .parquet extension."""
        csv_path = self._rotator.path()
        return csv_path.with_suffix(".parquet")

    def writerow(self, row: Sequence) -> Path:
        """Write a single row. Less efficient than writerows."""
        return self.writerows([row])

    def writerows(self, rows: Iterable[Sequence]) -> Path:
        """Write multiple rows efficiently - append to Parquet file."""
        with self._lock:
            path = self._get_path()

            # Convert rows to DataFrame
            rows_list = list(rows)
            if not rows_list:
                return path

            df = pd.DataFrame(rows_list, columns=self._headers)

            # Convert timestamp columns to datetime
            for col in df.columns:
                if "timestamp" in col:
                    df[col] = pd.to_datetime(df[col], unit="ms")

            # Append to existing file or create new one
            if path.exists():
                # Read existing data
                existing_df = pd.read_parquet(path)
                # Concatenate
                df = pd.concat([existing_df, df], ignore_index=True)

            # Write with compression
            df.to_parquet(
                path,
                engine="pyarrow",
                compression=self._compression,
                index=False,
            )

            return path


__all__ = ["RotatingParquetWriter"]
