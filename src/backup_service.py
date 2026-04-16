"""Nightly and on-demand SQLite backup per user."""

from __future__ import annotations

import logging
from pathlib import Path

import database as db
from config import UserConfig

logger = logging.getLogger(__name__)


def backup_user(user: UserConfig) -> tuple[bool, str]:
    """Copy db to backup_path with timestamp; prune old. Returns (ok, message)."""
    try:
        src = Path(user.db_path)
        if not src.exists():
            return False, "db missing"
        dest_dir = Path(user.backup_path)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = db.backup_db_file(str(src), dest_dir)
        removed = db.prune_backups(dest_dir, user.backup_retention)
        logger.info(
            "backup ok user=%s file=%s removed=%s",
            user.name,
            out.name,
            len(removed),
        )
        return True, str(out)
    except OSError as e:
        logger.error("backup failed user=%s: %s", user.name, e)
        return False, str(e)


def backup_all_users(users: list[UserConfig]) -> dict[str, tuple[bool, str]]:
    return {u.name: backup_user(u) for u in users}
