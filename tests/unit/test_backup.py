"""Backup service tests."""

from __future__ import annotations

from pathlib import Path

import database as db
from backup_service import backup_user
from config import UserConfig


def test_backup_creates_timestamped_file(tmp_path: Path) -> None:
    dbp = tmp_path / "u.sqlite"
    dbp.write_bytes(b"sqlite")
    u = UserConfig(
        name="u",
        garmin_email="a@a.com",
        garmin_password="p",
        api_key="k" * 32,
        token_cache_path=str(tmp_path / "t"),
        encryption_secret="e" * 16,
        db_path=str(dbp),
        backup_path=str(tmp_path / "bk"),
        backup_retention=7,
        timezone="UTC",
        rate_limit=30,
        initial_sync_days=7,
        reasoning_retention_days=90,
        goals=[],
    )
    ok, msg = backup_user(u)
    assert ok
    assert Path(msg).exists()
    assert "backup_" in Path(msg).name


def test_retention_prunes_oldest(tmp_path: Path) -> None:
    bk = tmp_path / "bk"
    bk.mkdir()
    for i in range(5):
        p = bk / f"backup_2026010{i}_000000.sqlite"
        p.write_text("x")
    removed = db.prune_backups(bk, 2)
    assert len(removed) == 3
    assert len(list(bk.glob("*.sqlite"))) == 2
