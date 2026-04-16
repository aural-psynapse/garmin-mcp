"""Sleep read tool."""

from __future__ import annotations

import json
from typing import Any

import database as db
from metrics import DB_HITS, TOOL_CALLS
from runtime import get_app_state
from validation import validate_date_range

from ._common import current_user, tool_enabled


def register(mcp) -> None:
    @mcp.tool(name="get_sleep")
    async def get_sleep(start_date: str, end_date: str | None = None) -> dict[str, Any]:
        if not tool_enabled("get_sleep"):
            return {"error": "tool disabled"}
        u = current_user()
        st = get_app_state()
        TOOL_CALLS.labels(user=u.name, tool="get_sleep").inc()
        d0, d1 = validate_date_range(start_date, end_date, st.config.max_date_range_days)
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        DB_HITS.labels(user=u.name).inc()
        last = db.get_last_sync_at(conn, u.name)
        cur = conn.execute(
            """SELECT * FROM sleep WHERE user_id=? AND calendar_date >= ? AND calendar_date <= ?
               AND status='active' ORDER BY calendar_date""",
            (u.name, d0.isoformat(), d1.isoformat()),
        )
        rows = list(cur)
        conn.close()
        nights = []
        for r in rows:
            raw = json.loads(r["raw_json"])
            nights.append(
                {
                    "date": r["calendar_date"],
                    "duration_s": r["duration_s"],
                    "score": r["score"],
                    "stages": json.loads(r["stages_json"]) if r["stages_json"] else None,
                    "raw": raw,
                }
            )
        return {
            "sleep": nights,
            "data_source": "cache",
            "last_sync_at": last,
        }
