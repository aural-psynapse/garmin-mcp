"""Middleware tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from config import AppConfig
from middleware import find_user_by_key


def test_find_user_by_key() -> None:
    root = Path(__file__).resolve().parents[2]
    raw = yaml.safe_load((root / "config.example.yaml").read_text())
    c = AppConfig.model_validate(raw)
    u = find_user_by_key(c, raw["users"][0]["api_key"])
    assert u is not None
    assert u.name == "alice"
    assert find_user_by_key(c, "wrong") is None
