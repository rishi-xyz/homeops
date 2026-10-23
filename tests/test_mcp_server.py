"""MCP smoke test over Streamable HTTP.

This starts the real HomeOps MCP server in-process on a free port, connects a
real MCP client, and checks the three things the hackathon checklist cares
about: the session initialises, the protocol version is 2025-11-25 or later,
and a tool call returns seeded data.
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import pytest
from homeops_core.config import Settings, get_settings
from homeops_mcp_server import server as mcp_server
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import LATEST_PROTOCOL_VERSION

REQUIRED_PROTOCOL_VERSION = "2025-11-25"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
async def mcp_url(settings: Settings) -> AsyncIterator[str]:
    """Run the MCP server over Streamable HTTP and yield its URL."""
    import uvicorn

    # Point the in-process server at the temporary test database.
    os.environ["HOMEOPS_HOME"] = str(settings.home)
    os.environ["HOMEOPS_DB_PATH"] = str(settings.db_path)
    get_settings.cache_clear()

    port = _free_port()
    app = mcp_server.server.streamable_http_app(streamable_http_path="/mcp")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.get_running_loop().create_task(server.serve())

    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:  # pragma: no cover - startup failure
        server.should_exit = True
        raise RuntimeError("MCP server did not start in time")

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    with suppress(asyncio.CancelledError):  # pragma: no cover - shutdown race
        await task
    get_settings.cache_clear()


@asynccontextmanager
async def _session(url: str) -> AsyncIterator[ClientSession]:
    async with (
        streamable_http_client(url) as (read, write, *_rest),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


@pytest.mark.asyncio
async def test_initialize_negotiates_required_protocol_version(mcp_url: str) -> None:
    """The session must negotiate MCP 2025-11-25 or later."""
    async with _session(mcp_url) as session:
        assert session.protocol_version is not None
        assert session.protocol_version >= REQUIRED_PROTOCOL_VERSION
        assert session.protocol_version <= LATEST_PROTOCOL_VERSION


@pytest.mark.asyncio
async def test_lists_expected_tools(mcp_url: str) -> None:
    """Every tool in the documented surface must be discoverable."""
    async with _session(mcp_url) as session:
        tools = await session.list_tools()
        names = {tool.name for tool in tools.tools}

    expected = {
        "list_assets",
        "get_asset_details",
        "create_asset",
        "search_maintenance_history",
        "log_maintenance_event",
        "create_reminder",
        "list_reminders",
        "complete_reminder",
        "snooze_reminder",
        "cancel_reminder",
        "get_technician_brief",
        "prepare_service_handoff",
        "list_demo_service_slots",
        "draft_demo_service_request",
        "confirm_demo_service_request",
        "list_service_requests",
        "list_providers",
    }
    assert expected.issubset(names)


@pytest.mark.asyncio
async def test_tools_have_typed_schemas(mcp_url: str) -> None:
    """Tool definitions must carry a validated input schema."""
    async with _session(mcp_url) as session:
        tools = await session.list_tools()
        by_name = {tool.name: tool for tool in tools.tools}

    assert by_name["list_assets"].input_schema["type"] == "object"
    properties = by_name["list_assets"].input_schema["properties"]
    assert "category" in properties
    assert by_name["get_asset_details"].input_schema["required"] == ["asset_id"]


@pytest.mark.asyncio
async def test_call_tool_returns_seeded_data(mcp_url: str) -> None:
    """A real tool call must return the seeded fictional household."""
    async with _session(mcp_url) as session:
        result = await session.call_tool("list_assets", {"limit": 10})

    assert result.is_error is not True
    payload = result.structured_content
    assert payload is not None
    assert payload["count"] >= 1
    asset_ids = {asset["asset_id"] for asset in payload["assets"]}
    assert "asset_washer_01" in asset_ids
    assert all(asset["is_demo"] for asset in payload["assets"])


@pytest.mark.asyncio
async def test_unknown_asset_returns_a_useful_error(mcp_url: str) -> None:
    """An unknown ID must produce an error result, not a stack trace."""
    async with _session(mcp_url) as session:
        result = await session.call_tool("get_asset_details", {"asset_id": "asset_missing"})

    assert result.is_error is True
    text = " ".join(block.text for block in result.content if hasattr(block, "text"))
    assert "asset_missing" in text
    assert "Traceback" not in text


@pytest.mark.asyncio
async def test_create_asset_persists_and_keeps_missing_warranty_unknown(mcp_url: str) -> None:
    """A created asset must be listed and must not claim a warranty it was not given."""
    async with _session(mcp_url) as session:
        result = await session.call_tool(
            "create_asset", {"name": "Fridge Freezer", "brand": "Example"}
        )
        assert result.is_error is not True
        payload = result.structured_content
        asset = payload["detail"]["asset"]
        assert asset["asset_id"].startswith("asset_")
        assert asset["warranty_end"] is None
        assert payload["detail"]["warranty"]["status"] == "unknown"

        listed = await session.call_tool("list_assets", {"limit": 100})

    ids = {item["asset_id"] for item in listed.structured_content["assets"]}
    assert asset["asset_id"] in ids
