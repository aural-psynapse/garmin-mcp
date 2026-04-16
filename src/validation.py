"""Input validation for tools."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(s: str) -> date:
    if not ISO_DATE.match(s):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(s)


def validate_date_range(
    start: str,
    end: str | None,
    max_days: int,
) -> tuple[date, date]:
    d0 = parse_iso_date(start)
    d1 = parse_iso_date(end) if end else d0
    if d1 < d0:
        raise ValueError("end before start")
    if (d1 - d0).days > max_days:
        raise ValueError(f"range exceeds {max_days} days")
    today = datetime.now(UTC).date()
    if d0 > today or d1 > today:
        raise ValueError("future date not allowed")
    return d0, d1
