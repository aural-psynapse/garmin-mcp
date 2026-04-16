"""Workout feeling log."""

from __future__ import annotations

from typing import Any

import database as db
from metrics import TOOL_CALLS
from ._common import current_user, tool_enabled


def register(mcp) -> None:
    @mcp.tool(name="log_workout_feeling")
    async def log_workout_feeling(
        activity_id: str,
        feeling: str,
        energy_level: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if not tool_enabled("log_workout_feeling"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="log_workout_feeling").inc()
        if energy_level not in ("low", "moderate", "high"):
            return {"error": "energy_level must be low|moderate|high"}
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        fid = db.insert_workout_feeling(conn, u.name, activity_id, feeling, energy_level, notes)
        conn.close()
        return {"id": fid, "ok": True}
