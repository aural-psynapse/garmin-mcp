"""Load and validate config.yaml via Pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class ToolToggles(BaseModel):
    get_recent_activities: bool = True
    get_activity_detail: bool = True
    get_sleep: bool = True
    get_training_status: bool = True
    get_training_readiness: bool = True
    get_historical_summary: bool = True
    get_my_context: bool = True
    suggest_next_workout: bool = True
    get_goal_progress: bool = True
    create_goal: bool = True
    complete_goal: bool = True
    list_goals: bool = True
    archive_goal: bool = True
    log_reasoning: bool = True
    log_workout_feeling: bool = True
    dismiss_flag: bool = True


class FlagRules(BaseModel):
    poor_sleep_streak_days: int = Field(default=3, ge=1)
    load_week_over_week_pct: float = Field(default=10.0, ge=0)
    goal_idle_days_before_deadline: int = Field(default=7, ge=1)
    pr_detection_enabled: bool = True


class UserConfig(BaseModel):
    name: str = Field(..., min_length=1)
    garmin_email: str
    garmin_password: str
    api_key: str = Field(..., min_length=8)
    token_cache_path: str
    encryption_secret: str = Field(..., min_length=8)
    db_path: str
    backup_path: str
    backup_retention: int = Field(default=7, ge=1)
    timezone: str = "UTC"
    rate_limit: int = Field(default=30, ge=1)
    initial_sync_days: int = Field(default=365, ge=1)
    reasoning_retention_days: int = Field(default=90, ge=1)
    goals: list[dict[str, Any]] = Field(default_factory=list)
    flag_rules: FlagRules = Field(default_factory=FlagRules)

    @field_validator("timezone")
    @classmethod
    def tz_ok(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Invalid timezone: {v}") from e
        return v


class AppConfig(BaseModel):
    port: int = Field(default=8765, ge=1, le=65535)
    log_level: str = Field(default="info")
    cloudflare_tunnel_token: str = Field(default="", description="Injected into cloudflared via compose")
    last_n_days: int = Field(default=30, ge=1)
    max_date_range_days: int = Field(default=90, ge=1)
    sync_interval_minutes: int = Field(default=30, ge=1)
    backup_schedule_time: str = Field(default="02:00", description="Local server time HH:MM")
    tools: ToolToggles = Field(default_factory=ToolToggles)
    users: list[UserConfig]

    @model_validator(mode="after")
    def unique_keys_and_names(self) -> AppConfig:
        keys = [u.api_key for u in self.users]
        names = [u.name for u in self.users]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate api_key in users")
        if len(set(names)) != len(names):
            raise ValueError("Duplicate user name in users")
        return self


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p.resolve()}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config.yaml must be a mapping at the root")
    return AppConfig.model_validate(raw)
