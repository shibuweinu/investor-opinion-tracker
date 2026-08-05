# mypy: ignore-errors
from __future__ import annotations

from .config import Settings
from .scheduling import schedule_hint


def build_server():
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError("请安装 MCP 依赖：pip install 'investor-opinion-tracker[mcp]'") from exc
    server = MCPServer("investor-opinion-tracker")

    @server.tool()
    def get_default_profile() -> dict:
        """Return the safe default trader profile."""
        return Settings().trader_profile.model_dump()

    @server.tool()
    def get_schedule_hint(kind: str = "daily") -> str:
        """Return a schedule suggestion without creating external state."""
        return schedule_hint(kind)

    return server


def main() -> None:
    build_server().run()
