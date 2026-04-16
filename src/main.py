"""FastMCP HTTP/SSE server: entrypoint, routes, lifespan, graceful shutdown."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app_state import AppState
from auth import GarminAuthManager
from backup_service import backup_all_users
from config import load_config
from metrics import metrics_bytes
from middleware import GarminMCPMiddleware
from runtime import set_app_state
from sync import run_sync
from tools import register_all

VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("garmin-mcp")

_config_path = os.environ.get("GARMIN_MCP_CONFIG", "config.yaml")
_cfg = load_config(_config_path)
_state = AppState(config=_cfg)
set_app_state(_state)

for u in _cfg.users:
    _state.auth_by_user[u.name] = GarminAuthManager(
        u.garmin_email,
        u.garmin_password,
        u.token_cache_path,
        u.encryption_secret,
        u.name,
    )

mcp = FastMCP(
    "garmin-mcp",
    instructions="Garmin Connect MCP — use get_my_context at conversation start.",
)


@mcp.prompt(
    name="analyze_new_workout",
    title="Analyze new workout",
    description="Structured post-workout analysis flow.",
)
async def analyze_new_workout_prompt() -> str:
    return """Follow this flow when the user asks to analyze a new workout or last run:
1. Call get_my_context if not already loaded.
2. get_recent_activities with limit 1 for the latest workout.
3. get_activity_detail for full metrics.
4. Compare vs goal target and 4-week trend; cross-check sleep and readiness.
5. log_reasoning with a one-line observation (optionally goal_id).
6. suggest_next_workout.
7. Ask how they felt and call log_workout_feeling with their answer."""


register_all(mcp)

_mcp_app = mcp.http_app(
    path="/mcp",
    transport="sse",
)


async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok", "version": VERSION})


async def metrics(request: Request) -> Response:
    return Response(metrics_bytes(), media_type="text/plain; version=0.0.4")


async def sync_username(request: Request) -> Response:
    name = request.path_params["username"]
    user = request.state.garmin_user
    if name != user.name:
        return JSONResponse(
            {"error": "forbidden", "detail": "API key does not match this user"},
            status_code=403,
        )
    auth = _state.auth_by_user.get(user.name)
    if not auth:
        return JSONResponse({"error": "no auth"}, status_code=500)
    try:
        result = await asyncio.to_thread(run_sync, user, auth, None)
        return JSONResponse(result)
    except Exception as e:
        logger.exception("sync failed")
        return JSONResponse({"error": str(e)}, status_code=500)


async def backup_all(request: Request) -> Response:
    results = backup_all_users(_cfg.users)
    return JSONResponse({k: {"ok": v[0], "msg": v[1]} for k, v in results.items()})


_shutdown_event = asyncio.Event()
_bg_tasks: list[asyncio.Task] = []


async def _periodic_sync() -> None:
    while not _shutdown_event.is_set():
        try:
            await asyncio.sleep(_cfg.sync_interval_minutes * 60)
        except asyncio.CancelledError:
            return
        if _shutdown_event.is_set():
            return
        for u in _cfg.users:
            if _shutdown_event.is_set():
                return
            auth = _state.auth_by_user.get(u.name)
            if not auth:
                continue
            try:
                await asyncio.to_thread(run_sync, u, auth, None)
            except Exception as e:
                logger.error("periodic sync %s: %s", u.name, e)


@asynccontextmanager
async def lifespan(_: Starlette):
    # One Garmin session + DB init per user: run_sync already connects, init_schema, and get_client().
    # Avoid a separate startup get_client() — that doubled SSO traffic on every boot.
    for u in _cfg.users:
        if u.name not in _state.auth_by_user:
            continue
        try:
            await asyncio.to_thread(run_sync, u, _state.auth_by_user[u.name], None)
        except Exception as e:
            logger.warning("initial sync user=%s: %s", u.name, e)
    t = asyncio.create_task(_periodic_sync())
    _bg_tasks.append(t)
    yield
    _shutdown_event.set()
    for t in _bg_tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    for auth in _state.auth_by_user.values():
        auth.close()


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/metrics", metrics, methods=["GET"]),
    Route("/sync/{username}", sync_username, methods=["POST"]),
    Route("/backup/all", backup_all, methods=["POST"]),
    Mount("/", _mcp_app),
]

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    middleware=[Middleware(GarminMCPMiddleware, state=_state)],
)


def _install_signal_handlers() -> None:
    def _h(*_: object) -> None:
        _shutdown_event.set()

    try:
        signal.signal(signal.SIGTERM, _h)
        signal.signal(signal.SIGINT, _h)
    except ValueError:
        pass


if __name__ == "__main__":
    import uvicorn

    _install_signal_handlers()
    uvicorn.run(app, host="0.0.0.0", port=_cfg.port)
