"""Activity read tools."""

from __future__ import annotations

import json
from typing import Any

import database as db
from metrics import DB_HITS, TOOL_CALLS
from runtime import get_app_state
from tzutil import to_local

from ._common import current_user, tool_enabled


def register(mcp) -> None:
    @mcp.tool(name="get_recent_activities")
    async def get_recent_activities(limit: int = 10, include_archived: bool = False) -> dict[str, Any]:
        if not tool_enabled("get_recent_activities"):
            return {"error": "tool disabled"}
        u = current_user()
        get_app_state()
        TOOL_CALLS.labels(user=u.name, tool="get_recent_activities").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        DB_HITS.labels(user=u.name).inc()
        last = db.get_last_sync_at(conn, u.name)
        rows = db.fetch_recent_activities(conn, u.name, limit, include_archived)
        conn.close()
        out = []
        for r in rows:
            out.append(
                {
                    "type": r["activity_type"],
                    "distance_km": r["distance_m"],
                    "duration_s": r["duration_s"],
                    "pace_s_per_km": r["pace_s_per_km"],
                    "date": to_local(r["start_time_utc"], u.timezone),
                    "avg_hr": r["avg_hr"],
                    "garmin_id": r["garmin_id"],
                    "status": r["status"],
                }
            )
        return {
            "activities": out,
            "data_source": "cache",
            "last_sync_at": last,
            "data_quality": "full",
        }

    @mcp.tool(name="get_activity_detail")
    async def get_activity_detail(activity_id: str, include_archived: bool = False) -> dict[str, Any]:
        if not tool_enabled("get_activity_detail"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="get_activity_detail").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        DB_HITS.labels(user=u.name).inc()
        last = db.get_last_sync_at(conn, u.name)
        row = db.get_activity(conn, u.name, activity_id)
        conn.close()
        if not row:
            return {"error": "not found", "activity_id": activity_id}
        if row["status"] != "active" and not include_archived:
            return {"error": "archived; set include_archived=true", "activity_id": activity_id}
        raw = json.loads(row["raw_json"])
        return {
            "detail": raw,
            "normalized": {
                "type": row["activity_type"],
                "distance_km": row["distance_m"],
                "duration_s": row["duration_s"],
                "avg_hr": row["avg_hr"],
                "pace_s_per_km": row["pace_s_per_km"],
                "start_local": to_local(row["start_time_utc"], u.timezone),
            },
            "data_source": "cache",
            "last_sync_at": last,
        }
