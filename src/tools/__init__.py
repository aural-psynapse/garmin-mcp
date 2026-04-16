"""Register all MCP tools and prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_all(mcp: FastMCP) -> None:
    from . import activities, context, feelings, flags, goals, history, sleep, training

    activities.register(mcp)
    sleep.register(mcp)
    training.register(mcp)
    context.register(mcp)
    goals.register(mcp)
    feelings.register(mcp)
    flags.register(mcp)
    history.register(mcp)
