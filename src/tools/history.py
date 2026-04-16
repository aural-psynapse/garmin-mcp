"""Historical reasoning summary."""

from __future__ import annotations

from typing import Any

import database as db
from metrics import DB_HITS, TOOL_CALLS

from ._common import current_user, tool_enabled


def register(mcp) -> None:
    @mcp.tool(name="get_historical_summary")
    async def get_historical_summary(limit: int = 20, include_archived: bool = False) -> dict[str, Any]:
        if not tool_enabled("get_historical_summary"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="get_historical_summary").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        DB_HITS.labels(user=u.name).inc()
        q = "SELECT * FROM reasonings WHERE user_id=?"
        if not include_archived:
            q += " AND archived=0"
        q += " ORDER BY created_at DESC LIMIT ?"
        rows = list(conn.execute(q, (u.name, limit)))
        conn.close()
        return {
            "entries": [
                {
                    "id": r["id"],
                    "tool": r["tool_name"],
                    "summary": r["summary"],
                    "created_at": r["created_at"],
                    "goal_id": r["goal_id"],
                }
                for r in rows
            ]
        }
