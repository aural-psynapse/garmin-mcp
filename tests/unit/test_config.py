"""Config loader tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config import AppConfig, load_config


def test_load_example_config(tmp_path: Path) -> None:
    ex = Path(__file__).resolve().parents[2] / "config.example.yaml"
    raw = yaml.safe_load(ex.read_text())
    raw["users"] = raw["users"][:1]
    raw["users"][0]["api_key"] = "x" * 32
    raw["users"][0]["encryption_secret"] = "e" * 16
    p = tmp_path / "c.yaml"
    p.write_text(yaml.dump(raw))
    c = load_config(p)
    assert isinstance(c, AppConfig)
    assert c.port == 8765


def test_duplicate_api_key_rejected(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(
        yaml.dump(
            {
                "users": [
                    {
                        "name": "a",
                        "garmin_email": "a@a.com",
                        "garmin_password": "p",
                        "api_key": "same-key-123456789012345678901234",
                        "token_cache_path": "/t/a",
                        "encryption_secret": "secret12345678901",
                        "db_path": "/d/a.sqlite",
                        "backup_path": "/b/a",
                        "backup_retention": 7,
                        "timezone": "UTC",
                        "rate_limit": 30,
                        "initial_sync_days": 365,
                        "reasoning_retention_days": 90,
                        "goals": [],
                        "flag_rules": {
                            "poor_sleep_streak_days": 3,
                            "load_week_over_week_pct": 10.0,
                            "goal_idle_days_before_deadline": 7,
                            "pr_detection_enabled": True,
                        },
                    },
                    {
                        "name": "b",
                        "garmin_email": "b@b.com",
                        "garmin_password": "p",
                        "api_key": "same-key-123456789012345678901234",
                        "token_cache_path": "/t/b",
                        "encryption_secret": "secret12345678902",
                        "db_path": "/d/b.sqlite",
                        "backup_path": "/b/b",
                        "backup_retention": 7,
                        "timezone": "UTC",
                        "rate_limit": 30,
                        "initial_sync_days": 365,
                        "reasoning_retention_days": 90,
                        "goals": [],
                        "flag_rules": {
                            "poor_sleep_streak_days": 3,
                            "load_week_over_week_pct": 10.0,
                            "goal_idle_days_before_deadline": 7,
                            "pr_detection_enabled": True,
                        },
                    },
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="Duplicate"):
        load_config(p)
