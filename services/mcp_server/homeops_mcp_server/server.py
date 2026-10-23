"""HomeOps MCP server - Streamable HTTP transport.

Run it with::

    python -m homeops_mcp_server.server

The server binds to loopback by default and exposes the HomeOps tool surface
described in ``docs/``. Every tool validates its arguments, bounds its result
size and returns structured data. The server never runs shell commands, never
executes free-form SQL, never fetches arbitrary URLs and never sends anything
on the user's behalf.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Annotated, Any

from homeops_core import db
from homeops_core.config import Settings, get_settings
from homeops_core.errors import HomeOpsError
from homeops_core.models import (
    AssetCategory,
    AssetDetail,
    AssetSummary,
    EventType,
    HandoffPayload,
    MaintenanceEventView,
    ReminderStatus,
    ReminderView,
    ServiceCategory,
    ServiceRequest,
    ServiceSlot,
    SourceType,
    TechnicianBrief,
)
from homeops_core.services import assets as assets_service
from homeops_core.services import brief as brief_service
from homeops_core.services import handoff as handoff_service
from homeops_core.services import maintenance as maintenance_service
from homeops_core.services import providers as providers_service
from homeops_core.services import reminders as reminders_service
from homeops_core.services import slots as slots_service
from homeops_core.timeutil import utcnow_iso
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

SERVER_NAME = "homeops"
SERVER_VERSION = "0.1.0"
SERVER_INSTRUCTIONS = (
    "HomeOps is a household maintenance assistant. It stores appliance records, warranty dates, "
    "maintenance history and reminders, and prepares technician briefs and provider handoffs. "
    "All seeded records are fictional demo data. Missing details stay unknown - never invent a "
    "purchase date, warranty term, repair, provider contact or timestamp."
)

MAX_LIST_LIMIT = 100
MAX_HISTORY_LIMIT = 50
MAX_SLOT_LIMIT = 20


# ---------------------------------------------------------------------------
# Result models (structured output schemas)
# ---------------------------------------------------------------------------


class ListAssetsResult(BaseModel):
    """Assets matching a list query."""

    assets: list[AssetSummary] = Field(default_factory=list)
    count: int = 0
    query: str | None = None
    category: AssetCategory | None = None
    warranty_basis_note: str = (
        "Warranty status is calculated from the dates saved in HomeOps and is not a verified "
        "manufacturer determination."
    )


class AssetDetailsResult(BaseModel):
    """A single asset with its warranty state and linked records."""

    detail: AssetDetail
    warranty_basis_note: str


class CreateAssetResult(BaseModel):
    """A newly created asset with its derived warranty state."""

    detail: AssetDetail
    created: bool = True
    notice: str = (
        "Asset stored from the details supplied. Purchase and warranty dates that were not "
        "supplied stay unknown; no warranty term is inferred."
    )
    warranty_basis_note: str


class MaintenanceSearchResult(BaseModel):
    """Matching maintenance records."""

    events: list[MaintenanceEventView] = Field(default_factory=list)
    count: int = 0
    matched: bool = False
    message: str = "No matching maintenance record was found in HomeOps."


class ReminderListResult(BaseModel):
    """Reminders with recomputed due state."""

    reminders: list[ReminderView] = Field(default_factory=list)
    count: int = 0
    now: str


class ServiceSlotListResult(BaseModel):
    """Fictional appointment slots."""

    slots: list[ServiceSlot] = Field(default_factory=list)
    count: int = 0
    notice: str = "Demo data: these slots are fictional and no real provider is contacted."


class DemoRequestResult(BaseModel):
    """A pending simulated request plus its confirmation reference."""

    request: ServiceRequest
    confirmation_token: str
    notice: str = (
        "Demo booking only - this is a simulation. No real service provider has been contacted, "
        "and the request is not confirmed until you explicitly confirm it."
    )


class DemoRequestListResult(BaseModel):
    """Simulated requests and their status."""

    requests: list[ServiceRequest] = Field(default_factory=list)
    count: int = 0
    notice: str = "All requests are local demo records. No real provider is involved."


class ProviderListResult(BaseModel):
    """Provider records, including which contact details exist."""

    providers: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    notice: str = "Seeded providers are fictional demo records."


# ---------------------------------------------------------------------------
# Server plumbing
# ---------------------------------------------------------------------------

server = MCPServer(
    name=SERVER_NAME,
    title="HomeOps household maintenance",
    version=SERVER_VERSION,
    instructions=SERVER_INSTRUCTIONS,
)


@contextmanager
def _db_session(settings: Settings) -> Iterator[Any]:
    """Open a transactional SQLite session for one tool call."""
    with db.session(settings) as conn:
        db.init_schema(conn)
        yield conn


def _audit(
    conn,
    tool_name: str,
    *,
    status: str,
    started: float,
    record_ids: list[str] | None = None,
    summary: str | None = None,
) -> None:
    """Record a short tool audit entry - no secrets, no raw conversation text."""
    with suppress(Exception):  # pragma: no cover - auditing must never break a tool
        conn.execute(
            """
            INSERT INTO tool_audit_events (
                audit_id, tool_name, created_at, result_status, duration_ms, record_ids, short_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"aud_{uuid.uuid4().hex[:12]}",
                tool_name,
                utcnow_iso(),
                status,
                int((time.perf_counter() - started) * 1000),
                json.dumps(record_ids or []),
                (summary or "")[:300],
            ),
        )


def _fail(exc: HomeOpsError) -> ToolError:
    """Turn a domain error into a client-safe tool error.

    The stable error code is embedded so the API can map the failure back onto
    the right HTTP status instead of returning a generic 200-with-error payload.
    """
    return ToolError(f"[{exc.code}] {exc.message}")


def _settings() -> Settings:
    settings = get_settings()
    settings.ensure_directories()
    return settings


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@server.tool(
    name="list_assets",
    title="List household assets",
    description=(
        "List or filter the household assets HomeOps knows about. Optionally filter by a text "
        "query (name, brand, model or location) and/or a category. Each result includes the "
        "warranty status derived from the dates saved in HomeOps."
    ),
    structured_output=True,
)
async def list_assets(
    query: Annotated[str | None, Field(description="Optional text to match against name, brand, model or location.")] = None,
    category: Annotated[AssetCategory | None, Field(description="Optional category filter.")] = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIST_LIMIT, description="Maximum number of assets to return.")] = 20,
) -> ListAssetsResult:
    """List household assets with their warranty status."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            items = assets_service.list_assets(
                conn,
                query=query,
                category=category,
                limit=limit,
                expiring_soon_days=settings.expiring_soon_days,
                timezone=settings.household_timezone,
            )
            _audit(
                conn,
                "list_assets",
                status="success",
                started=started,
                record_ids=[item.asset_id for item in items],
                summary=f"{len(items)} asset(s)",
            )
        return ListAssetsResult(
            assets=items, count=len(items), query=query, category=category
        )
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="get_asset_details",
    title="Get asset details",
    description=(
        "Get one asset with its saved purchase and warranty dates, provenance, manual and receipt "
        "references, plus the IDs of its recent maintenance events and open reminders. Unknown "
        "fields stay unknown."
    ),
    structured_output=True,
)
async def get_asset_details(
    asset_id: Annotated[str, Field(description="The asset_id to look up.")],
) -> AssetDetailsResult:
    """Get the full record for one household asset."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            detail = assets_service.get_asset_detail(
                conn,
                asset_id,
                expiring_soon_days=settings.expiring_soon_days,
                timezone=settings.household_timezone,
            )
            _audit(
                conn,
                "get_asset_details",
                status="success",
                started=started,
                record_ids=[detail.asset.asset_id, *detail.recent_event_ids],
                summary=f"{detail.asset.name} ({detail.warranty.status.value})",
            )
        return AssetDetailsResult(detail=detail, warranty_basis_note=detail.warranty.basis_note)
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="create_asset",
    title="Add a household asset",
    description=(
        "Add a new appliance or other household item to HomeOps, for example when the user buys "
        "or installs something. Store only the details the user actually provided: purchase and "
        "warranty dates that were not supplied stay unknown, and no warranty term is inferred."
    ),
    structured_output=True,
)
async def create_asset(
    name: Annotated[str, Field(min_length=1, max_length=200, description="Display name, for example 'Fridge Freezer'.")],
    category: Annotated[AssetCategory, Field(description="Asset category.")] = AssetCategory.APPLIANCE,
    location: Annotated[str | None, Field(max_length=200, description="Where the item is installed.")] = None,
    brand: Annotated[str | None, Field(max_length=200, description="Brand, only if the user stated it.")] = None,
    model: Annotated[str | None, Field(max_length=200, description="Model, only if the user stated it.")] = None,
    purchase_date: Annotated[str | None, Field(description="Optional ISO-8601 purchase date (YYYY-MM-DD).")] = None,
    warranty_start: Annotated[str | None, Field(description="Optional ISO-8601 warranty start date (YYYY-MM-DD).")] = None,
    warranty_end: Annotated[str | None, Field(description="Optional ISO-8601 warranty end date (YYYY-MM-DD).")] = None,
    timezone: Annotated[str | None, Field(max_length=64, description="IANA timezone used for warranty date maths.")] = None,
    manual_ref: Annotated[str | None, Field(max_length=200, description="Optional manual reference.")] = None,
    receipt_ref: Annotated[str | None, Field(max_length=200, description="Optional receipt reference.")] = None,
    source_type: Annotated[SourceType, Field(description="Where this record comes from.")] = SourceType.USER_ENTERED,
) -> CreateAssetResult:
    """Create and persist a new household asset."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            asset = assets_service.create_asset(
                conn,
                name=name,
                category=category,
                location=location,
                brand=brand,
                model=model,
                purchase_date=purchase_date,
                warranty_start=warranty_start,
                warranty_end=warranty_end,
                timezone=timezone or settings.household_timezone,
                manual_ref=manual_ref,
                receipt_ref=receipt_ref,
                source_type=source_type,
                is_demo=settings.demo_mode and source_type is SourceType.DEMO_SEED,
            )
            detail = assets_service.get_asset_detail(
                conn,
                asset.asset_id,
                expiring_soon_days=settings.expiring_soon_days,
                timezone=settings.household_timezone,
            )
            _audit(
                conn,
                "create_asset",
                status="success",
                started=started,
                record_ids=[asset.asset_id],
                summary=f"{asset.name} ({asset.category.value})",
            )
        return CreateAssetResult(
            detail=detail,
            warranty_basis_note=detail.warranty.basis_note,
        )
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="search_maintenance_history",
    title="Search maintenance history",
    description=(
        "Search previous issues, inspections, services, repairs and notes. Filter by asset, event "
        "type, free text, date range or a combination. An empty result is a valid answer - HomeOps "
        "never invents past work."
    ),
    structured_output=True,
)
async def search_maintenance_history(
    asset_id: Annotated[str | None, Field(description="Optional asset_id filter.")] = None,
    event_type: Annotated[EventType | None, Field(description="Optional event type filter.")] = None,
    query: Annotated[str | None, Field(description="Optional free-text search.")] = None,
    start_at: Annotated[str | None, Field(description="Optional ISO-8601 lower bound on the event time.")] = None,
    end_at: Annotated[str | None, Field(description="Optional ISO-8601 upper bound on the event time.")] = None,
    limit: Annotated[int, Field(ge=1, le=MAX_HISTORY_LIMIT, description="Maximum number of records to return.")] = 10,
) -> MaintenanceSearchResult:
    """Search the maintenance history."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            events = maintenance_service.search_maintenance_history(
                conn,
                asset_id=asset_id,
                event_type=event_type,
                query=query,
                start_at=start_at,
                end_at=end_at,
                limit=limit,
            )
            _audit(
                conn,
                "search_maintenance_history",
                status="success",
                started=started,
                record_ids=[event.event_id for event in events],
                summary=f"{len(events)} event(s)",
            )
        return MaintenanceSearchResult(
            events=events,
            count=len(events),
            matched=bool(events),
            message=(
                f"{len(events)} matching record(s)."
                if events
                else "No matching maintenance record was found in HomeOps."
            ),
        )
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="log_maintenance_event",
    title="Log a maintenance event",
    description=(
        "Record an issue, inspection, service visit, repair or note against an asset. "
        "'occurred_at' is when the work happened; the record creation time is stored separately."
    ),
    structured_output=True,
)
async def log_maintenance_event(
    event_type: Annotated[EventType, Field(description="The kind of record being logged.")],
    description: Annotated[str, Field(min_length=1, max_length=2000, description="What happened.")],
    asset_id: Annotated[str | None, Field(description="Optional asset this concerns.")] = None,
    occurred_at: Annotated[str | None, Field(description="Optional ISO-8601 timestamp with offset for when it happened.")] = None,
    outcome: Annotated[str | None, Field(max_length=1000, description="Optional result of the work.")] = None,
    location: Annotated[str | None, Field(max_length=200, description="Optional location.")] = None,
    provider_id: Annotated[str | None, Field(description="Optional provider that did the work.")] = None,
    source_type: Annotated[SourceType, Field(description="Where this record comes from.")] = SourceType.USER_ENTERED,
) -> MaintenanceEventView:
    """Log a new maintenance event."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            event = maintenance_service.log_maintenance_event(
                conn,
                event_type=event_type,
                description=description,
                asset_id=asset_id,
                occurred_at=occurred_at,
                outcome=outcome,
                location=location,
                provider_id=provider_id,
                source_type=source_type,
                is_demo=settings.demo_mode and source_type is SourceType.DEMO_SEED,
            )
            _audit(
                conn,
                "log_maintenance_event",
                status="success",
                started=started,
                record_ids=[event.event_id],
                summary=event.event_type.value,
            )
            return event
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="create_reminder",
    title="Create a reminder",
    description=(
        "Create a reminder for a warranty expiry, a service visit or any dated maintenance task. "
        "The due time must be an ISO-8601 timestamp with a timezone offset, and the timezone must "
        "be a valid IANA zone."
    ),
    structured_output=True,
)
async def create_reminder(
    title: Annotated[str, Field(min_length=1, max_length=200, description="What the reminder is about.")],
    due_at: Annotated[str, Field(description="ISO-8601 timestamp with offset for when it is due.")],
    timezone: Annotated[str, Field(description="IANA timezone the due time is expressed in.")] = "Europe/London",
    asset_id: Annotated[str | None, Field(description="Optional asset this reminder is about.")] = None,
    source_event_id: Annotated[str | None, Field(description="Optional maintenance event that triggered it.")] = None,
    recurrence: Annotated[str | None, Field(max_length=100, description="Optional recurrence descriptor.")] = None,
) -> ReminderView:
    """Create and persist a reminder."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            reminder = reminders_service.create_reminder(
                conn,
                title=title,
                due_at=due_at,
                timezone=timezone,
                asset_id=asset_id,
                source_event_id=source_event_id,
                recurrence=recurrence,
                is_demo=False,
            )
            _audit(
                conn,
                "create_reminder",
                status="success",
                started=started,
                record_ids=[reminder.reminder_id],
                summary=reminder.title[:120],
            )
            return reminder
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="list_reminders",
    title="List reminders",
    description=(
        "List reminders ordered by due time. The due state is recomputed from the stored due time "
        "on every call, so a completed reminder never reappears as due."
    ),
    structured_output=True,
)
async def list_reminders(
    status: Annotated[ReminderStatus | None, Field(description="Optional status filter.")] = None,
    asset_id: Annotated[str | None, Field(description="Optional asset_id filter.")] = None,
    from_at: Annotated[str | None, Field(description="Optional ISO-8601 lower bound on due time.")] = None,
    to_at: Annotated[str | None, Field(description="Optional ISO-8601 upper bound on due time.")] = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIST_LIMIT, description="Maximum number of reminders to return.")] = 20,
) -> ReminderListResult:
    """List reminders with their computed due state."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            items = reminders_service.list_reminders(
                conn,
                status=status,
                asset_id=asset_id,
                from_at=from_at,
                to_at=to_at,
                limit=limit,
            )
            _audit(
                conn,
                "list_reminders",
                status="success",
                started=started,
                record_ids=[item.reminder_id for item in items],
                summary=f"{len(items)} reminder(s)",
            )
        return ReminderListResult(reminders=items, count=len(items), now=utcnow_iso())
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="complete_reminder",
    title="Complete a reminder",
    description="Mark a reminder as done. Completing an already completed reminder is a no-op.",
    structured_output=True,
)
async def complete_reminder(
    reminder_id: Annotated[str, Field(description="The reminder_id to complete.")],
) -> ReminderView:
    """Mark a reminder complete."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            reminder = reminders_service.complete_reminder(conn, reminder_id)
            _audit(
                conn,
                "complete_reminder",
                status="success",
                started=started,
                record_ids=[reminder.reminder_id],
                summary=reminder.status.value,
            )
            return reminder
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="snooze_reminder",
    title="Snooze a reminder",
    description="Postpone a reminder to a new due time.",
    structured_output=True,
)
async def snooze_reminder(
    reminder_id: Annotated[str, Field(description="The reminder_id to postpone.")],
    due_at: Annotated[str, Field(description="The new ISO-8601 due timestamp with offset.")],
    timezone: Annotated[str | None, Field(description="Optional IANA timezone for the new due time.")] = None,
) -> ReminderView:
    """Postpone a reminder."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            reminder = reminders_service.snooze_reminder(
                conn, reminder_id, due_at=due_at, timezone=timezone
            )
            _audit(
                conn,
                "snooze_reminder",
                status="success",
                started=started,
                record_ids=[reminder.reminder_id],
                summary=reminder.due_at,
            )
            return reminder
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="cancel_reminder",
    title="Cancel a reminder",
    description="Cancel a reminder so it stops appearing as due.",
    structured_output=True,
)
async def cancel_reminder(
    reminder_id: Annotated[str, Field(description="The reminder_id to cancel.")],
) -> ReminderView:
    """Cancel a reminder."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            reminder = reminders_service.cancel_reminder(conn, reminder_id)
            _audit(
                conn,
                "cancel_reminder",
                status="success",
                started=started,
                record_ids=[reminder.reminder_id],
                summary=reminder.status.value,
            )
            return reminder
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="get_technician_brief",
    title="Build a technician brief",
    description=(
        "Build a brief for a technician from stored records only: the asset, its saved warranty "
        "information, the reported issue, related previous events and the details HomeOps does "
        "not know. Every fact carries the record ID it came from."
    ),
    structured_output=True,
)
async def get_technician_brief(
    event_id: Annotated[str | None, Field(description="Optional maintenance event the brief is about.")] = None,
    asset_id: Annotated[str | None, Field(description="Optional asset the brief is about.")] = None,
    include_history: Annotated[bool, Field(description="Include related previous maintenance records.")] = True,
) -> TechnicianBrief:
    """Build a record-grounded technician brief."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            brief = brief_service.build_technician_brief(
                conn,
                event_id=event_id,
                asset_id=asset_id,
                include_history=include_history,
                expiring_soon_days=settings.expiring_soon_days,
                timezone=settings.household_timezone,
            )
            _audit(
                conn,
                "get_technician_brief",
                status="success",
                started=started,
                record_ids=brief.record_ids,
                summary=f"{len(brief.facts)} fact(s)",
            )
            return brief
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="prepare_service_handoff",
    title="Prepare a provider handoff",
    description=(
        "Prepare a provider handoff for an issue: a Google Maps search link, a prefilled WhatsApp "
        "message when a valid phone number is stored, phone and email links, the provider's own "
        "booking page when a validated https URL is stored, and the technician brief. Nothing is "
        "sent or booked - the user reviews the recipient and message and then opens the link."
    ),
    structured_output=True,
)
async def prepare_service_handoff(
    service_category: Annotated[ServiceCategory, Field(description="The kind of service needed.")],
    event_id: Annotated[str | None, Field(description="Optional maintenance event describing the issue.")] = None,
    asset_id: Annotated[str | None, Field(description="Optional asset the issue concerns.")] = None,
    issue_description: Annotated[str | None, Field(max_length=500, description="Optional short issue summary from the user.")] = None,
    locality: Annotated[str | None, Field(max_length=120, description="Optional locality used for the Maps search.")] = None,
    provider_id: Annotated[str | None, Field(description="Optional provider to prepare the handoff for.")] = None,
) -> HandoffPayload:
    """Prepare a reviewable provider handoff."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            brief = None
            asset_name = None
            resolved_event = None

            if event_id:
                resolved_event = maintenance_service.get_event(conn, event_id)
                asset_id = asset_id or resolved_event.asset_id

            if asset_id:
                asset = assets_service.get_asset(conn, asset_id, timezone=settings.household_timezone)
                asset_name = asset.name

            if asset_id:
                brief = brief_service.build_technician_brief(
                    conn,
                    event_id=event_id,
                    asset_id=asset_id,
                    include_history=True,
                    expiring_soon_days=settings.expiring_soon_days,
                    timezone=settings.household_timezone,
                )

            provider = providers_service.find_provider_for_service(
                conn, service_category, provider_id=provider_id
            )
            resolved_locality = locality or (provider.locality if provider else None)

            summary_text = issue_description or (resolved_event.description if resolved_event else None)
            brief_lines = (
                [
                    f"{fact.label}: {fact.value}"
                    for fact in brief.facts[:6]
                    if not fact.is_unknown
                ]
                if brief
                else []
            )
            message = handoff_service.build_message_draft(
                asset_name=asset_name,
                service_category=service_category,
                issue_summary=summary_text,
                brief_lines=brief_lines,
                provider_name=provider.name if provider else None,
            )

            payload = handoff_service.build_handoff_payload(
                provider=provider,
                service_category=service_category,
                locality=resolved_locality,
                message_draft=message,
                technician_brief=brief,
                issue_event_id=event_id,
                asset_id=asset_id,
            )
            _audit(
                conn,
                "prepare_service_handoff",
                status="success",
                started=started,
                record_ids=brief.record_ids,
                summary=f"{len(payload.actions)} action(s)",
            )
            return payload
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="list_demo_service_slots",
    title="List demo service slots",
    description=(
        "List fictional appointment slots for a service category. These are demo records: they do "
        "not represent real availability and no provider is contacted."
    ),
    structured_output=True,
)
async def list_demo_service_slots(
    service_category: Annotated[ServiceCategory, Field(description="The service type to list slots for.")],
    preferred_date: Annotated[str | None, Field(description="Optional ISO-8601 date to filter on.")] = None,
    limit: Annotated[int, Field(ge=1, le=MAX_SLOT_LIMIT, description="Maximum number of slots to return.")] = 10,
) -> ServiceSlotListResult:
    """List fictional appointment slots."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            items = slots_service.list_demo_slots(
                conn,
                service_type=service_category,
                preferred_date=preferred_date,
                limit=limit,
            )
            _audit(
                conn,
                "list_demo_service_slots",
                status="success",
                started=started,
                record_ids=[item.slot_id for item in items],
                summary=f"{len(items)} slot(s)",
            )
        return ServiceSlotListResult(slots=items, count=len(items))
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="draft_demo_service_request",
    title="Draft a demo service request",
    description=(
        "Create a pending simulated service request for a fictional slot. The request stays "
        "'awaiting_user_action' and is never confirmed by this tool - only an explicit user "
        "confirmation can move it to 'confirmed_demo'."
    ),
    structured_output=True,
)
async def draft_demo_service_request(
    slot_id: Annotated[str, Field(description="The slot_id to request.")],
    event_id: Annotated[str | None, Field(description="Optional maintenance event the request is about.")] = None,
    note: Annotated[str | None, Field(max_length=500, description="Optional note to include.")] = None,
) -> DemoRequestResult:
    """Create a pending simulated service request."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            request, token = slots_service.draft_service_request(
                conn, slot_id=slot_id, event_id=event_id, note=note
            )
            _audit(
                conn,
                "draft_demo_service_request",
                status="success",
                started=started,
                record_ids=[request.request_id],
                summary=request.status.value,
            )
            return DemoRequestResult(request=request, confirmation_token=token)
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="confirm_demo_service_request",
    title="Confirm a demo service request",
    description=(
        "Confirm a pending simulated request using the confirmation reference returned when the "
        "request was drafted. The result is 'confirmed_demo' - a local demo record. No real "
        "provider is contacted and no real appointment is made. Confirming twice is a no-op."
    ),
    structured_output=True,
)
async def confirm_demo_service_request(
    request_id: Annotated[str, Field(description="The request_id to confirm.")],
    confirmation_token: Annotated[str, Field(description="The confirmation reference issued with the draft.")],
) -> ServiceRequest:
    """Confirm a pending simulated service request."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            request = slots_service.confirm_service_request(
                conn, request_id=request_id, confirmation_token=confirmation_token
            )
            _audit(
                conn,
                "confirm_demo_service_request",
                status="success",
                started=started,
                record_ids=[request.request_id],
                summary=request.status.value,
            )
            return request
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="list_service_requests",
    title="List demo service requests",
    description="List the local simulated service requests and their status.",
    structured_output=True,
)
async def list_service_requests(
    limit: Annotated[int, Field(ge=1, le=100, description="Maximum number of requests to return.")] = 20,
) -> DemoRequestListResult:
    """List simulated service requests."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            items = slots_service.list_requests(conn, limit=limit)
            _audit(
                conn,
                "list_service_requests",
                status="success",
                started=started,
                record_ids=[item.request_id for item in items],
                summary=f"{len(items)} request(s)",
            )
        return DemoRequestListResult(requests=items, count=len(items))
    except HomeOpsError as exc:
        raise _fail(exc) from exc


@server.tool(
    name="list_providers",
    title="List service providers",
    description=(
        "List the provider records HomeOps holds, including which contact details exist for each "
        "one. Missing contact details stay missing - HomeOps never invents a phone number."
    ),
    structured_output=True,
)
async def list_providers(
    service_category: Annotated[ServiceCategory | None, Field(description="Optional service type filter.")] = None,
) -> ProviderListResult:
    """List providers and their available contact details."""
    settings = _settings()
    started = time.perf_counter()
    try:
        with _db_session(settings) as conn:
            items = providers_service.list_providers(conn, service_category=service_category)
            payload = [
                {
                    "provider_id": item.provider_id,
                    "name": item.name,
                    "service_categories": [c.value for c in item.service_categories],
                    "phone": item.phone,
                    "email": item.email,
                    "booking_url": item.booking_url,
                    "locality": item.locality,
                    "has_phone": bool(item.phone),
                    "has_email": bool(item.email),
                    "has_booking_page": bool(item.booking_url),
                    "is_demo": item.is_demo,
                }
                for item in items
            ]
            _audit(
                conn,
                "list_providers",
                status="success",
                started=started,
                record_ids=[item.provider_id for item in items],
                summary=f"{len(items)} provider(s)",
            )
        return ProviderListResult(providers=payload, count=len(payload))
    except HomeOpsError as exc:
        raise _fail(exc) from exc


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@server.custom_route("/health", methods=["GET"])
async def health(_request):  # type: ignore[no-untyped-def]
    """Plain health endpoint for humans and scripts (not part of the MCP protocol)."""
    from starlette.responses import JSONResponse

    settings = get_settings()
    return JSONResponse(
        {
            "status": "ok",
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "transport": "streamable-http",
            "mcp_path": settings.mcp_path,
            "database": str(settings.db_path),
            "demo_mode": settings.demo_mode,
        }
    )


def create_app():
    """Return the Starlette application that serves the MCP endpoint."""
    settings = get_settings()
    settings.ensure_directories()
    return server.streamable_http_app(streamable_http_path=settings.mcp_path)


def main() -> None:
    """Run the MCP server over Streamable HTTP."""
    import uvicorn

    settings = get_settings()
    settings.ensure_directories()
    print(
        f"HomeOps MCP server on http://{settings.mcp_host}:{settings.mcp_port}{settings.mcp_path} "
        f"(transport=streamable-http)",
        flush=True,
    )
    uvicorn.run(
        create_app(),
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level="info",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
