"""Training status, readiness, suggest_next_workout."""

from __future__ import annotations

import json
from typing import Any

import database as db
from metrics import DB_HITS, TOOL_CALLS
from runtime import get_app_state

from ._common import current_user, tool_enabled


def register(mcp) -> None:
    @mcp.tool(name="get_training_status")
    async def get_training_status() -> dict[str, Any]:
        if not tool_enabled("get_training_status"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="get_training_status").inc()
        conn = db.connect(u.db_path)
        try:
            db.init_schema(conn)
            DB_HITS.labels(user=u.name).inc()
            last = db.get_last_sync_at(conn, u.name)
            row = db.get_latest_training_status(conn, u.name)
        finally:
            conn.close()
        if not row:
            return {"status": None, "data_source": "cache", "last_sync_at": last}
        return {
            "status": json.loads(row["raw_json"]),
            "data_source": "cache",
            "last_sync_at": last,
        }

    @mcp.tool(name="get_training_readiness")
    async def get_training_readiness() -> dict[str, Any]:
        if not tool_enabled("get_training_readiness"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="get_training_readiness").inc()
        conn = db.connect(u.db_path)
        try:
            db.init_schema(conn)
            DB_HITS.labels(user=u.name).inc()
            last = db.get_last_sync_at(conn, u.name)
            row = db.get_latest_training_readiness(conn, u.name)
        finally:
            conn.close()
        if not row:
            return {"readiness": None, "data_source": "cache", "last_sync_at": last}
        return {
            "readiness": json.loads(row["raw_json"]),
            "score": row["score"],
            "data_source": "cache",
            "last_sync_at": last,
        }

    @mcp.tool(name="suggest_next_workout")
    async def suggest_next_workout() -> dict[str, Any]:
        if not tool_enabled("suggest_next_workout"):
            return {"error": "tool disabled"}
        u = current_user()
        get_app_state()
        TOOL_CALLS.labels(user=u.name, tool="suggest_next_workout").inc()
        conn = db.connect(u.db_path)
        try:
            db.init_schema(conn)
            DB_HITS.labels(user=u.name).inc()
            readiness_row = db.get_latest_training_readiness(conn, u.name)
            status_row = db.get_latest_training_status(conn, u.name)
            goals = db.list_active_goals(conn, u.name)
            acts = db.fetch_recent_activities(conn, u.name, 3, False)
        finally:
            conn.close()

        dq: list[str] = []
        data_quality: str = "full"
        readiness_score = (
            float(readiness_row["score"]) if readiness_row and readiness_row["score"] is not None else None
        )
        if readiness_score is None:
            readiness_score = 65.0
            dq.append("Assumed moderate readiness (missing in DB).")
            data_quality = "partial"
        if not acts:
            dq.append("No recent activities; suggesting light baseline.")
            data_quality = "sparse"
        if not goals:
            dq.append("No active goals; suggestion based on load only.")
            if data_quality == "full":
                data_quality = "partial"

        if not acts and not status_row and not readiness_row and not goals:
            data_quality = "sparse"

        wtype = "easy_run"
        duration_min = 30
        zone = "Z2"
        if readiness_score < 50:
            wtype = "rest_or_walk"
            duration_min = 20
            zone = "Z1"
        reasoning = "Balanced with current readiness and recent load."
        goal_note = ""
        if goals:
            g = goals[0]
            goal_note = f"Aligned toward goal: {g['title']}"

        return {
            "workout_type": wtype,
            "duration_minutes": duration_min,
            "intensity_zone": zone,
            "reasoning": reasoning + (" " + goal_note if goal_note else ""),
            "goal_contribution": goal_note or None,
            "data_quality": data_quality,
            "assumptions_and_notes": dq,
        }
