"""Goals and reasoning write tools."""

from __future__ import annotations

from datetime import date
from typing import Any

import database as db
from metrics import DB_HITS, TOOL_CALLS
from runtime import get_app_state

from ._common import current_user, tool_enabled


def register(mcp) -> None:
    @mcp.tool(name="create_goal")
    async def create_goal(
        title: str,
        metric: str,
        target_value: float,
        description: str | None = None,
        target_date: str | None = None,
    ) -> dict[str, Any]:
        if not tool_enabled("create_goal"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="create_goal").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        gid = db.create_goal(conn, u.name, title, description, target_date, metric, target_value)
        conn.close()
        return {"goal_id": gid, "ok": True}

    @mcp.tool(name="complete_goal")
    async def complete_goal(goal_id: int) -> dict[str, Any]:
        if not tool_enabled("complete_goal"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="complete_goal").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        ok = db.complete_goal(conn, u.name, goal_id)
        conn.close()
        return {"ok": ok}

    @mcp.tool(name="list_goals")
    async def list_goals() -> dict[str, Any]:
        if not tool_enabled("list_goals"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="list_goals").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        rows = db.list_active_goals(conn, u.name)
        conn.close()
        return {"goals": [dict(r) for r in rows]}

    @mcp.tool(name="archive_goal")
    async def archive_goal(goal_id: int) -> dict[str, Any]:
        if not tool_enabled("archive_goal"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="archive_goal").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        ok = db.archive_goal_manual(conn, u.name, goal_id)
        conn.close()
        return {"ok": ok}

    @mcp.tool(name="log_reasoning")
    async def log_reasoning(
        tool_name: str,
        summary: str,
        goal_id: int | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if not tool_enabled("log_reasoning"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="log_reasoning").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        rid = db.insert_reasoning(conn, u.name, tool_name, {}, {}, summary, goal_id, tags)
        conn.close()
        return {"reasoning_id": rid, "ok": True}

    @mcp.tool(name="get_goal_progress")
    async def get_goal_progress() -> dict[str, Any]:
        if not tool_enabled("get_goal_progress"):
            return {"error": "tool disabled"}
        u = current_user()
        get_app_state()
        TOOL_CALLS.labels(user=u.name, tool="get_goal_progress").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        DB_HITS.labels(user=u.name).inc()
        goals = db.list_active_goals(conn, u.name)
        progress = []
        for g in goals:
            # Simplified: current value from latest activity distance if metric contains distance
            current = 0.0
            acts = db.fetch_recent_activities(conn, u.name, 50, False)
            if acts:
                current = float(acts[0]["distance_m"] or 0)
            target = float(g["target_value"])
            delta = target - current
            status = "on_track"
            if delta > target * 0.3:
                status = "behind"
            elif delta < 0:
                status = "achieved"
            td = g["target_date"]
            days_left = 999
            if td:
                try:
                    days_left = (date.fromisoformat(td[:10]) - date.today()).days
                except Exception:
                    pass
            if 0 < days_left < 14 and status == "behind":
                status = "at_risk"
            progress.append(
                {
                    "goal_id": g["id"],
                    "title": g["title"],
                    "metric": g["metric"],
                    "target": target,
                    "current_measured": current,
                    "delta_to_target": delta,
                    "estimated_completion": None,
                    "workouts_since_goal": len(acts),
                    "status": status,
                }
            )
        conn.close()
        return {"goals": progress, "data_source": "cache", "last_sync_at": None}
