"""Prometheus metrics (per-user labels where applicable)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, generate_latest

REG = CollectorRegistry()

TOOL_CALLS = Counter(
    "garmin_mcp_tool_calls_total",
    "MCP tool invocations",
    ["user", "tool"],
    registry=REG,
)
DB_HITS = Counter(
    "garmin_mcp_db_hits_total",
    "DB read operations in tools",
    ["user"],
    registry=REG,
)
SYNC_CALLS = Counter(
    "garmin_mcp_sync_calls_total",
    "Garmin sync invocations",
    ["user"],
    registry=REG,
)
AUTH_REFRESH = Counter(
    "garmin_mcp_auth_refresh_total",
    "Auth refresh / re-login",
    ["user"],
    registry=REG,
)
RATE_LIMIT_HITS = Counter(
    "garmin_mcp_rate_limit_hits_total",
    "Rate limit 429 responses",
    ["user"],
    registry=REG,
)
ERRORS = Counter(
    "garmin_mcp_errors_total",
    "Unhandled or logged errors",
    ["user", "kind"],
    registry=REG,
)


def metrics_bytes() -> bytes:
    return generate_latest(REG)
