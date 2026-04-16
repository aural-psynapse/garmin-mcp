from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def to_local(iso_utc: str | None, tz_name: str) -> str | None:
    if not iso_utc:
        return None
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(ZoneInfo(tz_name)).isoformat()
    except Exception:
        return iso_utc
