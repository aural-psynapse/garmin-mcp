"""Bootstrap context tool."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import database as db
from metrics import SYNC_CALLS, TOOL_CALLS
from runtime import get_app_state
from sync import run_sync

from ._common import current_user, tool_enabled


def register(mcp) -> None:
    @mcp.tool(name="get_my_context")
    async def get_my_context() -> dict[str, Any]:
        if not tool_enabled("get_my_context"):
            return {"error": "tool disabled"}
        u = current_user()
        st = get_app_state()
        TOOL_CALLS.labels(user=u.name, tool="get_my_context").inc()
        auth = st.auth_by_user.get(u.name)
        if not auth:
            return {"error": "auth not initialized"}
        SYNC_CALLS.labels(user=u.name).inc()
        try:
            sync_result = run_sync(u, auth, full_historical_days=None)
        except Exception as e:
            return {"error": "sync_failed", "detail": str(e)}

        conn = db.connect(u.db_path)
        db.init_schema(conn)
        last = db.get_last_sync_at(conn, u.name)
        goals = db.list_active_goals(conn, u.name)
        ts = db.get_latest_training_status(conn, u.name)
        tr = db.get_latest_training_readiness(conn, u.name)
        flags = db.list_unacknowledged_flags(conn, u.name)
        reason_rows = db.recent_reasonings(conn, u.name, 7, 50)
        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        reason_rows = [r for r in reason_rows if r["created_at"] >= cutoff]
        conn.close()

        goals_summary = [
            {"id": g["id"], "title": g["title"], "metric": g["metric"], "target": g["target_value"]} for g in goals
        ]
        reasonings = []
        for r in reason_rows:
            reasonings.append(
                {
                    "tool": r["tool_name"],
                    "summary": r["summary"],
                    "created_at": r["created_at"],
                }
            )

        return {
            "sync": sync_result,
            "active_goals": goals_summary,
            "last_7d_reasonings": reasonings,
            "training_status": json.loads(ts["raw_json"]) if ts else None,
            "training_readiness_score": float(tr["score"]) if tr and tr["score"] is not None else None,
            "last_sync_at": last,
            "unacknowledged_flags": [
                {"id": f["id"], "type": f["flag_type"], "payload": json.loads(f["payload_json"] or "{}")} for f in flags
            ],
            "data_source": "cache",
        }
