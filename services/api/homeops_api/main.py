"""FastAPI application entry point.

Run with::

    uvicorn homeops_api.main:app --host 127.0.0.1 --port 8000

The application binds to loopback by default. It opens an MCP client session
against the HomeOps MCP server on startup so that every assistant action is a
real MCP call.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from homeops_core.config import Settings, get_settings
from homeops_core.errors import MCPUnavailableError

from .mcp_client import MCPClientManager
from .orchestrator import Orchestrator
from .routes import router
from .summary import build_summary_provider

logger = logging.getLogger("homeops.api")

DESCRIPTION = """
HomeOps orchestrator API.

The browser talks to this service; this service talks to the HomeOps MCP
server over Streamable HTTP with a real MCP client. Every assistant action in
the UI is a real MCP tool call, and the returned tool trace is shown in the
activity panel.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application."""
    resolved = settings or get_settings()
    resolved.ensure_directories()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        mcp = MCPClientManager(resolved.mcp_url)
        app.state.mcp = mcp
        app.state.settings = resolved
        app.state.orchestrator = Orchestrator(mcp, resolved, build_summary_provider(resolved))
        try:
            await mcp.start()
            logger.info(
                "MCP session established with %s (protocol %s)",
                resolved.mcp_url,
                mcp.protocol_version,
            )
        except MCPUnavailableError as exc:
            # The API still starts so /health can report the problem clearly.
            logger.warning("MCP server unavailable at startup: %s", exc.message)
        try:
            yield
        finally:
            await mcp.stop()

    app = FastAPI(
        title="HomeOps API",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:3001",
            "http://localhost:3001",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": "homeops-api",
            "docs": "/docs",
            "health": "/health",
            "mcp_url": resolved.mcp_url,
        }

    return app


app = create_app()


def main() -> None:  # pragma: no cover - manual entry point
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "homeops_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
