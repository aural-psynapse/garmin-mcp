"""Pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_config_path(tmp_path: Path) -> Path:
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["users"] = [
        {
            "name": "tester",
            "garmin_email": "t@example.com",
            "garmin_password": "pw",
            "api_key": "test-key-12345678901234567890",
            "token_cache_path": str(tmp_path / "tok"),
            "encryption_secret": "enc-secret-123456789012",
            "db_path": str(tmp_path / "db.sqlite"),
            "backup_path": str(tmp_path / "backups"),
            "backup_retention": 3,
            "timezone": "UTC",
            "rate_limit": 100,
            "initial_sync_days": 7,
            "reasoning_retention_days": 90,
            "goals": [],
            "flag_rules": {
                "poor_sleep_streak_days": 3,
                "load_week_over_week_pct": 10.0,
                "goal_idle_days_before_deadline": 7,
                "pr_detection_enabled": True,
            },
        }
    ]
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.dump(raw))
    os.environ["GARMIN_MCP_CONFIG"] = str(p)
    return p
