"""Configuration for the standalone MCP server."""

from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerConfig(BaseSettings):
    server_name: str = "supportops-mcp"
    transport: str = os.getenv("MCP_TRANSPORT", "stdio")
    sse_host: str = os.getenv("MCP_SSE_HOST", "127.0.0.1")
    sse_port: int = int(os.getenv("MCP_SSE_PORT", "8100"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./supportops.db")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


config = MCPServerConfig()