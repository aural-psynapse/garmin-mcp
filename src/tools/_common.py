"""Shared helpers for MCP tools."""

from __future__ import annotations


from fastmcp.server.dependencies import get_http_request

from config import UserConfig
from runtime import get_app_state


def current_user() -> UserConfig:
    req = get_http_request()
    u = getattr(req.state, "garmin_user", None)
    if u is None:
        raise RuntimeError("User context missing")
    return u


def tool_enabled(name: str) -> bool:
    st = get_app_state()
    t = st.config.tools
    return bool(getattr(t, name, True))
