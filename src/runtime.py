"""Mutable process state set from main."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app_state import AppState

_state: AppState | None = None


def set_app_state(s: AppState) -> None:
    global _state
    _state = s


def get_app_state() -> AppState:
    if _state is None:
        raise RuntimeError("App not initialized")
    return _state
