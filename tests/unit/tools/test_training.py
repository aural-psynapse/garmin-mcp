"""Training / suggest_next_workout tests."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.filterwarnings("ignore:unclosed database:ResourceWarning")
@pytest.mark.asyncio
async def test_suggest_sparse_when_no_data():
    """suggest_next_workout returns structured response with data_quality when DB is empty.

    Filter: pytest-cov + mock teardown can emit ResourceWarning despite the tool closing the DB
    (asserted via ProgrammingError below).
    """
    import tools.training as tr

    with (
        patch.object(tr, "current_user") as cu,
        patch.object(tr, "get_app_state") as gas,
        patch.object(tr.db, "connect") as conn_fn,
        patch.object(tr.db, "init_schema"),
        patch.object(tr.db, "get_latest_training_readiness", return_value=None),
        patch.object(tr.db, "get_latest_training_status", return_value=None),
        patch.object(tr.db, "list_active_goals", return_value=[]),
        patch.object(tr.db, "fetch_recent_activities", return_value=[]),
        patch.object(tr, "tool_enabled", return_value=True),
        patch.object(tr, "TOOL_CALLS") as tc,
    ):
        cu.return_value = SimpleNamespace(name="u", timezone="UTC", db_path=":memory:")
        gas.return_value = MagicMock()
        c = sqlite3.connect(":memory:")
        conn_fn.return_value = c
        tc.labels.return_value.inc = MagicMock()
        # Re-register to capture function
        from fastmcp import FastMCP

        m = FastMCP("x")
        tr.register(m)
        t = await m.get_tool("suggest_next_workout")
        r = await t.run({})
        body = r.structured_content if hasattr(r, "structured_content") else r
        assert body["data_quality"] in ("sparse", "partial")
        with pytest.raises(sqlite3.ProgrammingError):
            c.execute("SELECT 1")
