"""Per-user SQLite: schema, WAL, queries, backup helpers."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_locks: dict[str, threading.RLock] = {}
_global_lock = threading.Lock()


def _db_lock(db_path: str) -> threading.RLock:
    with _global_lock:
        if db_path not in _locks:
            _locks[db_path] = threading.RLock()
        return _locks[db_path]


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open SQLite connection; WAL must be first pragma."""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS activities (
            garmin_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            activity_type TEXT,
            start_time_utc TEXT,
            distance_m REAL,
            duration_s REAL,
            avg_hr REAL,
            pace_s_per_km REAL,
            status TEXT NOT NULL DEFAULT 'active',
            archived_at TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (garmin_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_act_user_start ON activities(user_id, start_time_utc);

        CREATE TABLE IF NOT EXISTS sleep (
            sleep_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            calendar_date TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            duration_s REAL,
            score REAL,
            stages_json TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            archived_at TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (sleep_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS training_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            archived_at TEXT,
            version INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS training_readiness (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            score REAL,
            status TEXT NOT NULL DEFAULT 'active',
            archived_at TEXT,
            version INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            duration_ms INTEGER,
            record_counts_json TEXT,
            status TEXT NOT NULL,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS reasonings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            params_json TEXT,
            response_json TEXT,
            summary TEXT,
            goal_id INTEGER,
            tags_json TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reason_user_created ON reasonings(user_id, created_at);

        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            target_date TEXT,
            metric TEXT NOT NULL,
            target_value REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            archived_at TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            flag_type TEXT NOT NULL,
            payload_json TEXT,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            acknowledged_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_flags_user_ack ON flags(user_id, acknowledged);

        CREATE TABLE IF NOT EXISTS workout_feelings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            activity_id TEXT NOT NULL,
            feeling TEXT NOT NULL,
            energy_level TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str, user_id: str) -> None:
        self.db_path = db_path
        self.user_id = user_id
        self._conn: sqlite3.Connection | None = None

    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self.db_path)
            init_schema(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# --- Queries used by tools (simplified; production would add more filters) ---


def get_last_sync_at(conn: sqlite3.Connection, user_id: str) -> str | None:
    row = conn.execute(
        "SELECT completed_at FROM sync_log WHERE user_id=? AND status='ok' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return row["completed_at"] if row else None


def insert_sync_log_start(conn: sqlite3.Connection, user_id: str) -> int:
    now = utc_now_iso()
    cur = conn.execute(
        "INSERT INTO sync_log (user_id, started_at, status) VALUES (?,?,?)",
        (user_id, now, "running"),
    )
    conn.commit()
    return int(cur.lastrowid)


def complete_sync_log(
    conn: sqlite3.Connection,
    sync_id: int,
    duration_ms: int,
    counts: dict[str, int],
    status: str = "ok",
    error: str | None = None,
) -> None:
    conn.execute(
        """UPDATE sync_log SET completed_at=?, duration_ms=?, record_counts_json=?, status=?, error=?
           WHERE id=?""",
        (utc_now_iso(), duration_ms, json.dumps(counts), status, error, sync_id),
    )
    conn.commit()


def upsert_activity(
    conn: sqlite3.Connection,
    user_id: str,
    garmin_id: str,
    raw: dict[str, Any],
    normalized: dict[str, Any],
) -> None:
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO activities (garmin_id, user_id, raw_json, activity_type, start_time_utc,
           distance_m, duration_s, avg_hr, pace_s_per_km, status, version, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(garmin_id, user_id) DO UPDATE SET
           raw_json=excluded.raw_json, activity_type=excluded.activity_type,
           start_time_utc=excluded.start_time_utc, distance_m=excluded.distance_m,
           duration_s=excluded.duration_s, avg_hr=excluded.avg_hr, pace_s_per_km=excluded.pace_s_per_km,
           status='active', archived_at=NULL, version=activities.version+1, updated_at=excluded.updated_at""",
        (
            garmin_id,
            user_id,
            json.dumps(raw),
            normalized.get("type"),
            normalized.get("start_time_utc"),
            normalized.get("distance_m"),
            normalized.get("duration_s"),
            normalized.get("avg_hr"),
            normalized.get("pace_s_per_km"),
            "active",
            1,
            now,
        ),
    )
    conn.commit()


def archive_missing_activities(conn: sqlite3.Connection, user_id: str, seen_ids: set[str]) -> int:
    """Mark activities not in seen_ids as archived (soft)."""
    now = utc_now_iso()
    cur = conn.execute("SELECT garmin_id FROM activities WHERE user_id=? AND status='active'", (user_id,))
    archived = 0
    for row in cur:
        gid = row["garmin_id"]
        if gid not in seen_ids:
            conn.execute(
                "UPDATE activities SET status='archived', archived_at=? WHERE garmin_id=? AND user_id=?",
                (now, gid, user_id),
            )
            archived += 1
    conn.commit()
    return archived


def fetch_recent_activities(
    conn: sqlite3.Connection,
    user_id: str,
    limit: int,
    include_archived: bool = False,
) -> list[sqlite3.Row]:
    q = "SELECT * FROM activities WHERE user_id=?"
    if not include_archived:
        q += " AND status='active'"
    q += " ORDER BY start_time_utc DESC LIMIT ?"
    return list(conn.execute(q, (user_id, limit)).fetchall())


def get_activity(conn: sqlite3.Connection, user_id: str, garmin_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM activities WHERE garmin_id=? AND user_id=?",
        (garmin_id, user_id),
    ).fetchone()


def upsert_sleep_row(
    conn: sqlite3.Connection,
    user_id: str,
    sleep_id: str,
    calendar_date: str,
    raw: dict[str, Any],
    duration_s: float | None,
    score: float | None,
    stages: dict[str, Any] | None,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO sleep (sleep_id, user_id, calendar_date, raw_json, duration_s, score, stages_json, version, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(sleep_id, user_id) DO UPDATE SET
           raw_json=excluded.raw_json, duration_s=excluded.duration_s, score=excluded.score,
           stages_json=excluded.stages_json, status='active', archived_at=NULL, version=sleep.version+1, updated_at=excluded.updated_at""",
        (
            sleep_id,
            user_id,
            calendar_date,
            json.dumps(raw),
            duration_s,
            score,
            json.dumps(stages) if stages else None,
            1,
            now,
        ),
    )
    conn.commit()


def upsert_training_status(conn: sqlite3.Connection, user_id: str, raw: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO training_status (user_id, recorded_at, raw_json) VALUES (?,?,?)",
        (user_id, utc_now_iso(), json.dumps(raw)),
    )
    conn.commit()


def upsert_training_readiness(conn: sqlite3.Connection, user_id: str, raw: dict[str, Any], score: float | None) -> None:
    conn.execute(
        "INSERT INTO training_readiness (user_id, recorded_at, raw_json, score) VALUES (?,?,?,?)",
        (user_id, utc_now_iso(), json.dumps(raw), score),
    )
    conn.commit()


def get_latest_training_status(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM training_status WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def get_latest_training_readiness(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM training_readiness WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def insert_flag(
    conn: sqlite3.Connection,
    user_id: str,
    flag_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO flags (user_id, flag_type, payload_json, acknowledged, created_at) VALUES (?,?,?,?,?)",
        (user_id, flag_type, json.dumps(payload or {}), 0, utc_now_iso()),
    )
    conn.commit()


def list_unacknowledged_flags(conn: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM flags WHERE user_id=? AND acknowledged=0 ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    )


def dismiss_flag_by_id(conn: sqlite3.Connection, user_id: str, flag_id: int) -> bool:
    cur = conn.execute(
        "UPDATE flags SET acknowledged=1, acknowledged_at=? WHERE id=? AND user_id=?",
        (utc_now_iso(), flag_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def insert_reasoning(
    conn: sqlite3.Connection,
    user_id: str,
    tool_name: str,
    params: dict[str, Any],
    response: dict[str, Any],
    summary: str | None,
    goal_id: int | None,
    tags: list[str] | None,
) -> int:
    cur = conn.execute(
        """INSERT INTO reasonings (user_id, tool_name, params_json, response_json, summary, goal_id, tags_json, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            user_id,
            tool_name,
            json.dumps(params),
            json.dumps(response),
            summary,
            goal_id,
            json.dumps(tags or []),
            utc_now_iso(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def recent_reasonings(
    conn: sqlite3.Connection, user_id: str, days: int, limit: int = 50
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """SELECT * FROM reasonings WHERE user_id=? AND archived=0
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    )


def create_goal(
    conn: sqlite3.Connection,
    user_id: str,
    title: str,
    description: str | None,
    target_date: str | None,
    metric: str,
    target_value: float,
) -> int:
    cur = conn.execute(
        """INSERT INTO goals (user_id, title, description, target_date, metric, target_value, status, created_at)
           VALUES (?,?,?,?,?,?, 'active', ?)""",
        (user_id, title, description, target_date, metric, target_value, utc_now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_active_goals(conn: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM goals WHERE user_id=? AND status='active' ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    )


def archive_goal_reasonings(conn: sqlite3.Connection, user_id: str, goal_id: int) -> None:
    conn.execute(
        "UPDATE reasonings SET archived=1 WHERE user_id=? AND goal_id=?",
        (user_id, goal_id),
    )
    conn.commit()


def complete_goal(conn: sqlite3.Connection, user_id: str, goal_id: int) -> bool:
    row = conn.execute(
        "UPDATE goals SET status='completed', archived_at=? WHERE id=? AND user_id=? AND status='active'",
        (utc_now_iso(), goal_id, user_id),
    )
    conn.commit()
    if row.rowcount:
        archive_goal_reasonings(conn, user_id, goal_id)
        return True
    return False


def archive_goal_manual(conn: sqlite3.Connection, user_id: str, goal_id: int) -> bool:
    row = conn.execute(
        "UPDATE goals SET status='archived', archived_at=? WHERE id=? AND user_id=? AND status='active'",
        (utc_now_iso(), goal_id, user_id),
    )
    conn.commit()
    if row.rowcount:
        archive_goal_reasonings(conn, user_id, goal_id)
        return True
    return False


def insert_workout_feeling(
    conn: sqlite3.Connection,
    user_id: str,
    activity_id: str,
    feeling: str,
    energy_level: str,
    notes: str | None,
) -> int:
    cur = conn.execute(
        """INSERT INTO workout_feelings (user_id, activity_id, feeling, energy_level, notes, created_at)
           VALUES (?,?,?,?,?,?)""",
        (user_id, activity_id, feeling, energy_level, notes, utc_now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def prune_old_untagged_reasonings(conn: sqlite3.Connection, user_id: str, retention_days: int) -> int:
    # Simplified: delete reasonings with no goal_id older than retention
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    cur = conn.execute(
        "DELETE FROM reasonings WHERE user_id=? AND goal_id IS NULL AND created_at < ?",
        (user_id, cutoff),
    )
    conn.commit()
    return cur.rowcount


def backup_db_file(db_path: str, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"backup_{ts}.sqlite"
    shutil.copy2(db_path, dest)
    return dest


def prune_backups(backup_dir: Path, retention: int) -> list[Path]:
    files = sorted(backup_dir.glob("backup_*.sqlite"), key=lambda p: p.stat().st_mtime)
    removed: list[Path] = []
    while len(files) > retention:
        oldest = files.pop(0)
        try:
            oldest.unlink()
            removed.append(oldest)
        except OSError:
            break
    return removed
