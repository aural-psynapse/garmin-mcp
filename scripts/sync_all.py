#!/usr/bin/env python3
"""Trigger POST /sync/{username} for every user in config.yaml (requires running server)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    cfg_path = os.environ.get("GARMIN_MCP_CONFIG", str(ROOT / "config.yaml"))
    base = os.environ.get("GARMIN_MCP_URL", "http://127.0.0.1:8765").rstrip("/")
    raw = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    users = raw.get("users") or []
    if not users:
        print("No users in config", file=sys.stderr)
        return 1
    try:
        httpx.get(f"{base}/health", timeout=5.0)
    except Exception as e:
        print(f"Server not reachable at {base}: {e}", file=sys.stderr)
        print("Start the server (e.g. make up) before make sync.", file=sys.stderr)
        return 1
    for u in users:
        name = u["name"]
        key = u["api_key"]
        url = f"{base}/sync/{name}"
        try:
            r = httpx.post(url, headers={"X-API-Key": key}, timeout=600.0)
            if r.status_code == 200:
                print(f"{name}: OK {r.json()}")
            else:
                print(f"{name}: FAIL {r.status_code} {r.text}")
        except Exception as ex:
            print(f"{name}: ERROR {ex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
