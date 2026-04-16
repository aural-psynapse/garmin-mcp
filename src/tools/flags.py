"""Dismiss proactive flags."""

from __future__ import annotations

from typing import Any

import database as db
from metrics import TOOL_CALLS
from ._common import current_user, tool_enabled


def register(mcp) -> None:
    @mcp.tool(name="dismiss_flag")
    async def dismiss_flag(flag_id: int) -> dict[str, Any]:
        if not tool_enabled("dismiss_flag"):
            return {"error": "tool disabled"}
        u = current_user()
        TOOL_CALLS.labels(user=u.name, tool="dismiss_flag").inc()
        conn = db.connect(u.db_path)
        db.init_schema(conn)
        ok = db.dismiss_flag_by_id(conn, u.name, flag_id)
        conn.close()
        return {"ok": ok}
