"""E2E-style ASGI tests (no real Garmin)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
import yaml
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


@pytest.fixture
def client(tmp_path, monkeypatch):
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    u = raw["users"][0]
    u["db_path"] = str(tmp_path / "e2e.sqlite")
    u["token_cache_path"] = str(tmp_path / "tok")
    u["backup_path"] = str(tmp_path / "bk")
    cfgp = tmp_path / "cfg.yaml"
    cfgp.write_text(yaml.dump(raw))
    monkeypatch.setenv("GARMIN_MCP_CONFIG", str(cfgp))
    sys.path.insert(0, str(SRC))
    for mod in list(sys.modules.keys()):
        if mod == "main" or mod.startswith("main.") or mod in (
            "config",
            "app_state",
            "middleware",
            "runtime",
            "metrics",
            "database",
            "auth",
            "sync",
            "backup_service",
        ):
            sys.modules.pop(mod, None)
    import main as main_mod

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_health_no_auth(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


def test_metrics_401_without_key(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 401


def test_sync_403_wrong_user(client: TestClient) -> None:
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    alice_key = raw["users"][0]["api_key"]
    r = client.post("/sync/bob", headers={"X-API-Key": alice_key})
    assert r.status_code == 403
