"""Configuration for the standalone MCP server."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerConfig(BaseSettings):
    server_name: str = "supportops-mcp"
    transport: str = Field(default="stdio", validation_alias="MCP_TRANSPORT")
    sse_host: str = Field(default="127.0.0.1", validation_alias="MCP_SSE_HOST")
    sse_port: int = Field(default=8100, validation_alias="MCP_SSE_PORT")
    database_url: str = Field(
        default="sqlite:///./supportops.db", validation_alias="DATABASE_URL"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


config = MCPServerConfig()