"""API-level tests.

The important test for the hackathon checklist is
``test_assistant_reply_is_backed_by_real_mcp_calls``: it starts the real MCP
server and the real FastAPI app, then drives the assistant endpoint and proves
the answer came from genuine MCP tool calls.

The MCP server runs in a background thread with its own event loop so the test
loop never has to share anyio cancel scopes with the server's serve() task.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from collections.abc import AsyncIterator

import httpx
import pytest
import uvicorn
from homeops_core.config import Settings, build_settings, get_settings
from homeops_mcp_server import server as mcp_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _ServerThread:
    """Runs one uvicorn server on its own event loop in a background thread."""

    def __init__(self, app, port: int) -> None:
        self._config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self._server = uvicorn.Server(self._config)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._server.serve())

    def start(self) -> None:
        self._thread.start()
        for _ in range(400):
            if self._server.started:
                return
            import time

            time.sleep(0.025)
        raise RuntimeError("test server did not start in time")

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


@pytest.fixture()
async def api_client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """Run the real MCP server plus the real API and yield an HTTP client."""
    os.environ["HOMEOPS_HOME"] = str(settings.home)
    os.environ["HOMEOPS_DB_PATH"] = str(settings.db_path)
    os.environ["HOMEOPS_SEED_DIR"] = str(settings.seed_dir)
    get_settings.cache_clear()

    mcp_port = _free_port()
    mcp_app = mcp_server.server.streamable_http_app(streamable_http_path="/mcp")
    mcp_server_thread = _ServerThread(mcp_app, mcp_port)
    mcp_server_thread.start()

    api_settings = build_settings(
        {
            **os.environ,
            "HOMEOPS_MCP_URL": f"http://127.0.0.1:{mcp_port}/mcp",
            "HOMEOPS_HOME": str(settings.home),
            "HOMEOPS_DB_PATH": str(settings.db_path),
        }
    )
    from homeops_api.main import create_app

    api_app = create_app(api_settings)
    api_port = _free_port()
    api_thread = _ServerThread(api_app, api_port)
    api_thread.start()

    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{api_port}", timeout=30.0) as client:
        yield client

    api_thread.stop()
    mcp_server_thread.stop()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_health_reports_a_live_mcp_session(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mcp"]["connected"] is True
    assert payload["mcp"]["protocol_version"] >= "2025-11-25"


@pytest.mark.asyncio
async def test_assistant_reply_is_backed_by_real_mcp_calls(api_client: httpx.AsyncClient) -> None:
    """The assistant answer must carry a real, non-empty MCP tool trace."""
    response = await api_client.post(
        "/api/assistant/message",
        json={"message": "Is my washing machine still under warranty?", "conversation_id": "pytest"},
    )
    assert response.status_code == 200
    turn = response.json()

    assert turn["intent"] == "warranty"
    names = [entry["name"] for entry in turn["tool_trace"]]
    assert "list_assets" in names
    assert "get_asset_details" in names
    # Every recorded call must have really succeeded against the MCP server.
    assert all(entry["status"] == "success" for entry in turn["tool_trace"])
    # The answer must reference the seeded, fictional record.
    assert "asset_washer_01" in turn["reply"]
    assert "fictional demo record" in turn["reply"]


@pytest.mark.asyncio
async def test_assets_endpoint_goes_through_the_mcp_server(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/assets")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert all(asset["is_demo"] for asset in payload["assets"])


@pytest.mark.asyncio
async def test_demo_request_cannot_be_confirmed_without_the_token(api_client: httpx.AsyncClient) -> None:
    slots = (await api_client.get("/api/demo/slots?service_category=appliance_repair")).json()
    assert slots["slots"], "the seed must provide a demo slot"
    slot_id = slots["slots"][0]["slot_id"]

    drafted = (await api_client.post("/api/demo-requests", json={"slot_id": slot_id})).json()
    request_id = drafted["request"]["request_id"]
    token = drafted["confirmation_token"]
    assert drafted["request"]["status"] == "awaiting_user_action"

    # A wrong reference must be refused with a meaningful HTTP status.
    wrong = await api_client.post(
        f"/api/demo-requests/{request_id}/confirm", json={"confirmation_token": "definitely-wrong"}
    )
    assert wrong.status_code == 409
    pending = (await api_client.get("/api/demo-requests")).json()
    match = next(item for item in pending["requests"] if item["request_id"] == request_id)
    assert match["status"] == "awaiting_user_action"

    # The issued reference confirms it as a local demo record only.
    confirmed = await api_client.post(
        f"/api/demo-requests/{request_id}/confirm", json={"confirmation_token": token}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed_demo"

    # Confirming twice is idempotent.
    again = await api_client.post(
        f"/api/demo-requests/{request_id}/confirm", json={"confirmation_token": token}
    )
    assert again.status_code == 200
    assert again.json()["status"] == "confirmed_demo"


@pytest.mark.asyncio
async def test_mcp_tools_endpoint_lists_the_running_server_tools(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/mcp/tools")
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["tools"]}
    assert {"list_assets", "prepare_service_handoff", "confirm_demo_service_request"}.issubset(names)


@pytest.mark.asyncio
async def test_unknown_asset_maps_to_a_404(api_client: httpx.AsyncClient) -> None:
    """A domain 'not found' from the MCP tool must not be a generic 200."""
    response = await api_client.get("/api/assets/asset_missing")
    assert response.status_code == 404
