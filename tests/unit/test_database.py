"""Database layer tests."""

from __future__ import annotations

import sqlite3

import database as db


def test_wal_first_pragma(tmp_path) -> None:
    p = tmp_path / "t.sqlite"
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE x(a int)")
    conn.close()
    with sqlite3.connect(str(p)) as c2:
        jm = c2.execute("PRAGMA journal_mode").fetchone()[0]
    assert jm.upper() == "WAL"


def test_connect_helper(tmp_path) -> None:
    p = tmp_path / "d.sqlite"
    c = db.connect(p)
    jm = c.execute("PRAGMA journal_mode").fetchone()[0]
    assert jm.upper() == "WAL"
    c.close()
