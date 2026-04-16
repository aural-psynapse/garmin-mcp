"""Process-wide application state (config, auth managers, sync)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auth import GarminAuthManager
    from config import AppConfig


@dataclass
class AppState:
    config: "AppConfig"
    auth_by_user: dict[str, "GarminAuthManager"] = field(default_factory=dict)
    shutting_down: bool = False
