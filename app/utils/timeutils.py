"""Time utilities for handling timezone aware timestamps."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

import pytz

DEFAULT_TZ = pytz.timezone("America/Mexico_City")


def now_local_utc() -> Tuple[datetime, datetime]:
    """Return tuple of (local_time, utc_time) with timezone awareness."""
    utc_now = datetime.now(timezone.utc)
    local_now = utc_now.astimezone(DEFAULT_TZ)
    return local_now, utc_now


def format_timestamp(dt: datetime) -> str:
    """Return ISO8601 formatted string with timezone info."""
    return dt.isoformat()


def localize(dt: datetime) -> datetime:
    """Attach default timezone if naive or convert to default timezone."""
    if dt.tzinfo is None:
        return DEFAULT_TZ.localize(dt)
    return dt.astimezone(DEFAULT_TZ)


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC timezone."""
    if dt.tzinfo is None:
        dt = DEFAULT_TZ.localize(dt)
    return dt.astimezone(timezone.utc)


__all__ = ["DEFAULT_TZ", "now_local_utc", "format_timestamp", "localize", "to_utc"]
