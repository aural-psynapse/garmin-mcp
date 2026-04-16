# Repository guide (for developers and AI agents)

## Purpose

This repo implements a **self-hosted Garmin Connect MCP server**: FastMCP over HTTP/SSE, per-user API keys, SQLite cache with WAL, encrypted Garmin tokens, background sync, optional Cloudflare Tunnel, and an agentic companion layer (bootstrap context, workout prompt, goals, flags, feelings).

## Architecture (request flow)

Claude → (Tunnel) → `garmin-mcp` → Starlette middleware (`X-API-Key`, rate limit) → FastMCP SSE (`/mcp`) → tools → SQLite. Garmin API is called **only** from `sync.py` (and `get_my_context` triggers sync before reads).

## File tree (annotated)

- `src/main.py` — FastMCP app, routes `/health`, `/metrics`, `/sync/{username}`, `/backup/all`, mounts MCP SSE.
- `src/config.py` — Pydantic config loader.
- `src/auth.py` — Garmin login + encrypted garth token cache.
- `src/database.py` — SQLite schema, WAL, queries, backup helpers.
- `src/sync.py` — Garmin sync + flag evaluation.
- `src/middleware.py` — API key + rate limiting.
- `src/metrics.py` — Prometheus registry.
- `src/backup_service.py` — Per-user SQLite file backup.
- `src/tools/*.py` — MCP tools and registrations.
- `tests/` — pytest unit and e2e tests.
- `pyproject.toml` — Ruff (lint/format) and pytest defaults; optional hooks in `.pre-commit-config.yaml`.
- `docker-compose.yml` — `garmin-mcp` + `cloudflared`.
- `Makefile` — Operational shortcuts.

## Delta sync

- If `sync_log` has a successful completion, subsequent syncs use a date-bounded window from the last completion.
- First boot uses `initial_sync_days` for historical activities.

## Concurrency model

The sync service and MCP tool handlers can run concurrently; **every** SQLite connection runs `PRAGMA journal_mode=WAL` first so readers and writers coexist without classic SQLite locking issues. Scale is intended for personal/family use; beyond ~10 users consider PostgreSQL.

## Goals and reasoning lifecycle

- Goals live in `goals`; reasonings in `reasonings` with optional `goal_id`.
- Completing or archiving a goal archives linked reasonings.
- Untagged reasonings are pruned after `reasoning_retention_days`.

## Backup strategy

Timestamped `backup_*.sqlite` files per user under `backup_path`, retention pruning.

## Write tools vs read tools

Write tools: goal management, `log_reasoning`, `log_workout_feeling`, `dismiss_flag`. Read tools query SQLite only (except `get_my_context`, which triggers sync then reads).

## Custom instruction snippet

See `README.md` — users should instruct Claude to call `get_my_context` at the start of every conversation.

## Known limitations

- Garmin MFA not supported (must disable MFA).
- Unofficial Garmin API via `garminconnect`; rate limits may apply.
- `pr_achieved` flag is stubbed.
