"""Starlette middleware: API key -> user, rate limit."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app_state import AppState
from config import UserConfig
from metrics import RATE_LIMIT_HITS

logger = logging.getLogger(__name__)

API_KEY_HEADER = "x-api-key"


def find_user_by_key(cfg, key: str | None) -> UserConfig | None:
    if not key:
        return None
    for u in cfg.users:
        if u.api_key == key:
            return u
    return None


class GarminMCPMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, state: AppState) -> None:
        super().__init__(app)
        self.state = state
        self._hits: dict[str, deque[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path in ("/health", "/"):
            return await call_next(request)

        key = request.headers.get(API_KEY_HEADER)
        user = find_user_by_key(self.state.config, key)
        if user is None:
            return JSONResponse({"error": "unauthorized", "detail": "Invalid or missing X-API-Key"}, status_code=401)

        now = time.monotonic()
        dq = self._hits.setdefault(user.name, deque())
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= user.rate_limit:
            RATE_LIMIT_HITS.labels(user=user.name).inc()
            return JSONResponse(
                {"error": "rate_limited", "detail": "Too many requests per minute"},
                status_code=429,
            )
        dq.append(now)

        request.state.garmin_user = user
        return await call_next(request)
