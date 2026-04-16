# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-16

### Added

- Multi-user FastMCP server with HTTP/SSE transport and Cloudflare Tunnel support
- SQLite-backed cache with WAL mode, delta sync, versioned archival, goals, reasonings, flags, workout feelings
- Agentic companion tools: `get_my_context`, `analyze_new_workout` prompt, `suggest_next_workout`, goal progress, feelings, flags
- Starlette middleware for `X-API-Key` authentication and per-user rate limiting
- Encrypted Garmin token cache (Fernet), Prometheus `/metrics`, `/health` with version
- Docker Compose with `garmin-mcp` and `cloudflared`, Makefile targets, CI workflow, and test suite
