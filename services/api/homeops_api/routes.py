"""HTTP API consumed by the web simulator.

The browser only ever talks to this API. Every route that represents a
primary HomeOps action goes through the MCP client to the running MCP server,
so the UI always reflects real tool calls.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from homeops_core.errors import HomeOpsError
from pydantic import BaseModel, Field

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AssistantMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    conversation_id: str | None = Field(default=None, max_length=120)


class CreateReminderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: str = Field(min_length=1)
    timezone: str = Field(default="Europe/London", max_length=64)
    asset_id: str | None = Field(default=None, max_length=120)
    recurrence: str | None = Field(default=None, max_length=100)


class CreateAssetRequest(BaseModel):
    """A new household item. Omitted dates stay unknown."""

    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    purchase_date: str | None = Field(default=None, max_length=20)
    warranty_start: str | None = Field(default=None, max_length=20)
    warranty_end: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=64)
    manual_ref: str | None = Field(default=None, max_length=200)
    receipt_ref: str | None = Field(default=None, max_length=200)


class HandoffRequest(BaseModel):
    service_category: str = Field(min_length=1, max_length=60)
    asset_id: str | None = Field(default=None, max_length=120)
    event_id: str | None = Field(default=None, max_length=120)
    issue_description: str | None = Field(default=None, max_length=500)
    locality: str | None = Field(default=None, max_length=120)
    provider_id: str | None = Field(default=None, max_length=120)


class DemoRequestCreate(BaseModel):
    slot_id: str = Field(min_length=1, max_length=120)
    event_id: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


class DemoRequestConfirm(BaseModel):
    confirmation_token: str = Field(min_length=1, max_length=200)


class ResetRequest(BaseModel):
    confirm: bool = Field(default=False, description="Must be true to wipe the local demo data.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _orchestrator(request: Request) -> Any:
    return request.app.state.orchestrator


def _mcp(request: Request) -> Any:
    return request.app.state.mcp


def _handle_error(exc: HomeOpsError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail=exc.to_dict())


# ---------------------------------------------------------------------------
# Health and metadata
# ---------------------------------------------------------------------------


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Service health without secrets."""
    settings = request.app.state.settings
    mcp = _mcp(request)
    return {
        "status": "ok",
        "service": "homeops-api",
        "version": request.app.version,
        "mcp": {
            "url": mcp.url,
            "connected": mcp.connected,
            "protocol_version": mcp.protocol_version,
            "server_info": mcp.server_info,
            "last_error": mcp.last_error,
        },
        "summary_provider": settings.summary_provider,
        "demo_mode": settings.demo_mode,
        "household_timezone": settings.household_timezone,
        "database": str(settings.db_path),
    }


@router.get("/api/mcp/tools")
async def mcp_tools(request: Request) -> dict[str, Any]:
    """The tools the running MCP server exposes."""
    try:
        tools = await _mcp(request).list_tools()
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return {"count": len(tools), "tools": tools}


# ---------------------------------------------------------------------------
# Assistant
# ---------------------------------------------------------------------------


@router.post("/api/assistant/message")
async def assistant_message(payload: AssistantMessageRequest, request: Request) -> dict[str, Any]:
    """Run one assistant turn through the MCP-backed orchestrator."""
    orchestrator = _orchestrator(request)
    turn = await orchestrator.handle(payload.message, payload.conversation_id)
    return turn.to_dict()


# ---------------------------------------------------------------------------
# Assets, reminders, maintenance
# ---------------------------------------------------------------------------


@router.get("/api/assets")
async def list_assets(request: Request, query: str | None = None, category: str | None = None) -> dict[str, Any]:
    """List household assets (through the MCP server)."""
    arguments: dict[str, Any] = {"limit": 100}
    if query:
        arguments["query"] = query
    if category:
        arguments["category"] = category
    try:
        payload, _record = await _mcp(request).call_tool("list_assets", arguments)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return payload


@router.get("/api/assets/{asset_id}")
async def asset_details(asset_id: str, request: Request) -> dict[str, Any]:
    """One asset with its warranty state."""
    try:
        payload, _record = await _mcp(request).call_tool("get_asset_details", {"asset_id": asset_id})
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return payload


@router.post("/api/assets", status_code=201)
async def create_asset(payload: CreateAssetRequest, request: Request) -> dict[str, Any]:
    """Add a household item through the MCP server."""
    arguments = {key: value for key, value in payload.model_dump().items() if value is not None}
    try:
        result, _record = await _mcp(request).call_tool("create_asset", arguments)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.get("/api/reminders")
async def list_reminders(request: Request, status: str | None = None, asset_id: str | None = None) -> dict[str, Any]:
    """Reminders with recomputed due state."""
    arguments: dict[str, Any] = {"limit": 100}
    if status:
        arguments["status"] = status
    if asset_id:
        arguments["asset_id"] = asset_id
    try:
        payload, _record = await _mcp(request).call_tool("list_reminders", arguments)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return payload


@router.post("/api/reminders")
async def create_reminder(payload: CreateReminderRequest, request: Request) -> dict[str, Any]:
    """Create a reminder through the MCP server."""
    arguments = payload.model_dump()
    arguments = {key: value for key, value in arguments.items() if value is not None}
    try:
        result, _record = await _mcp(request).call_tool("create_reminder", arguments)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.post("/api/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str, request: Request) -> dict[str, Any]:
    """Mark a reminder complete (idempotent)."""
    try:
        result, _record = await _mcp(request).call_tool("complete_reminder", {"reminder_id": reminder_id})
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.get("/api/maintenance")
async def list_maintenance(
    request: Request,
    asset_id: str | None = None,
    event_type: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Search the maintenance history."""
    arguments: dict[str, Any] = {"limit": 50}
    if asset_id:
        arguments["asset_id"] = asset_id
    if event_type:
        arguments["event_type"] = event_type
    if query:
        arguments["query"] = query
    try:
        result, _record = await _mcp(request).call_tool("search_maintenance_history", arguments)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.post("/api/maintenance")
async def log_maintenance(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    """Log a maintenance event."""
    try:
        result, _record = await _mcp(request).call_tool("log_maintenance_event", payload)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


# ---------------------------------------------------------------------------
# Provider handoff
# ---------------------------------------------------------------------------


@router.get("/api/providers")
async def list_providers(request: Request, service_category: str | None = None) -> dict[str, Any]:
    """Providers and which contact details they hold."""
    arguments: dict[str, Any] = {}
    if service_category:
        arguments["service_category"] = service_category
    try:
        result, _record = await _mcp(request).call_tool("list_providers", arguments)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.post("/api/handoff/prepare")
async def prepare_handoff(payload: HandoffRequest, request: Request) -> dict[str, Any]:
    """Prepare a reviewable handoff. Nothing is sent or booked here."""
    arguments = payload.model_dump()
    arguments = {key: value for key, value in arguments.items() if value is not None}
    try:
        result, _record = await _mcp(request).call_tool("prepare_service_handoff", arguments)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


# ---------------------------------------------------------------------------
# Simulated bookings
# ---------------------------------------------------------------------------


@router.get("/api/demo/slots")
async def demo_slots(request: Request, service_category: str = "appliance_repair") -> dict[str, Any]:
    """Fictional appointment slots."""
    try:
        result, _record = await _mcp(request).call_tool(
            "list_demo_service_slots", {"service_category": service_category, "limit": 20}
        )
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.get("/api/demo-requests")
async def list_demo_requests(request: Request) -> dict[str, Any]:
    """Local simulated requests."""
    try:
        result, _record = await _mcp(request).call_tool("list_service_requests", {"limit": 50})
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.post("/api/demo-requests")
async def create_demo_request(payload: DemoRequestCreate, request: Request) -> dict[str, Any]:
    """Draft a simulated request. It stays pending until it is confirmed."""
    arguments = payload.model_dump()
    arguments = {key: value for key, value in arguments.items() if value is not None}
    try:
        result, _record = await _mcp(request).call_tool("draft_demo_service_request", arguments)
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.post("/api/demo-requests/{request_id}/confirm")
async def confirm_demo_request(
    request_id: str, payload: DemoRequestConfirm, request: Request
) -> dict[str, Any]:
    """Confirm a pending simulated request with its confirmation reference."""
    try:
        result, _record = await _mcp(request).call_tool(
            "confirm_demo_service_request",
            {"request_id": request_id, "confirmation_token": payload.confirmation_token},
        )
    except HomeOpsError as exc:
        raise _handle_error(exc) from exc
    return result


@router.post("/api/demo/reset")
async def reset_demo(request: Request, payload: ResetRequest) -> dict[str, Any]:
    """Reset the local demo data. Requires an explicit confirmation."""
    settings = request.app.state.settings
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail={"error": "confirmation_required", "message": "Send confirm=true to reset the demo data."},
        )
    if not settings.demo_mode:
        raise HTTPException(
            status_code=403,
            detail={"error": "reset_disabled", "message": "Demo reset is disabled in this configuration."},
        )
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "reset_local_only",
                "message": "The demo reset is restricted to local requests.",
            },
        )

    from homeops_core.seed import seed_database

    counts = seed_database(settings, reset=True)
    return {"status": "reset", "loaded": counts, "demo_mode": True}
