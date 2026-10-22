"""Domain models and tool-facing schemas.

Two groups of models live here:

* **Entities** mirror the SQLite tables one-to-one.
* **Views** are the read models returned by the MCP tools and the API - they
  add derived information (warranty status, overdue flags) and deliberately
  keep unknown fields as ``None`` so nothing is ever invented.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceType(StrEnum):
    """Where a record came from."""

    USER_ENTERED = "user_entered"
    DEMO_SEED = "demo_seed"
    PROVIDER_REPORTED = "provider_reported"


class AssetCategory(StrEnum):
    APPLIANCE = "appliance"
    FIXTURE = "fixture"
    HVAC = "hvac"
    OUTDOOR = "outdoor"
    ELECTRONICS = "electronics"
    OTHER = "other"


class EventType(StrEnum):
    ISSUE = "issue"
    INSPECTION = "inspection"
    SERVICE = "service"
    REPAIR = "repair"
    NOTE = "note"


class ReminderStatus(StrEnum):
    PENDING = "pending"
    DUE = "due"
    COMPLETED = "completed"
    SNOOZED = "snoozed"
    CANCELLED = "cancelled"


class RequestStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_USER_ACTION = "awaiting_user_action"
    HANDOFF_OPENED = "handoff_opened"
    SUBMITTED_BY_USER = "submitted_by_user"
    CONFIRMED = "confirmed"
    CONFIRMED_DEMO = "confirmed_demo"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WarrantyStatus(StrEnum):
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class ServiceCategory(StrEnum):
    """Service types HomeOps can prepare a handoff for."""

    APPLIANCE_REPAIR = "appliance_repair"
    WASHING_MACHINE = "washing_machine"
    REFRIGERATION = "refrigeration"
    HEATING = "heating"
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    GARDEN = "garden"
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class Asset(BaseModel):
    """A household item HomeOps tracks."""

    model_config = ConfigDict(str_strip_whitespace=True)

    asset_id: str
    name: str
    category: AssetCategory
    location: str | None = None
    brand: str | None = None
    model: str | None = None
    purchase_date: date | None = None
    warranty_start: date | None = None
    warranty_end: date | None = None
    timezone: str = "Europe/London"
    manual_ref: str | None = None
    receipt_ref: str | None = None
    source_type: SourceType = SourceType.USER_ENTERED
    source_ref: str | None = None
    is_demo: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class MaintenanceEvent(BaseModel):
    """An issue, inspection, service visit, repair or note."""

    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: str
    asset_id: str | None = None
    event_type: EventType
    description: str
    occurred_at: str | None = None
    created_at: str | None = None
    outcome: str | None = None
    provider_id: str | None = None
    location: str | None = None
    source_type: SourceType = SourceType.USER_ENTERED
    source_ref: str | None = None
    is_demo: bool = False


class Reminder(BaseModel):
    """A dated reminder, optionally attached to an asset or event."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reminder_id: str
    asset_id: str | None = None
    title: str
    due_at: str
    timezone: str = "Europe/London"
    status: ReminderStatus = ReminderStatus.PENDING
    recurrence: str | None = None
    source_event_id: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    is_demo: bool = False


class Provider(BaseModel):
    """A service provider. Seeded providers are fictional demo records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: str
    name: str
    service_categories: list[ServiceCategory] = Field(default_factory=list)
    phone: str | None = None
    email: str | None = None
    booking_url: str | None = None
    locality: str | None = None
    source_type: SourceType = SourceType.DEMO_SEED
    source_ref: str | None = None
    is_demo: bool = False


class ServiceSlot(BaseModel):
    """A fictional appointment slot used by the simulated booking flow."""

    model_config = ConfigDict(str_strip_whitespace=True)

    slot_id: str
    provider_id: str
    service_type: ServiceCategory
    starts_at: str
    ends_at: str
    status: str = "available"
    is_demo: bool = True


class ServiceRequest(BaseModel):
    """A simulated service request. Never represents a real booking."""

    model_config = ConfigDict(str_strip_whitespace=True)

    request_id: str
    event_id: str | None = None
    provider_id: str | None = None
    slot_id: str | None = None
    status: RequestStatus = RequestStatus.DRAFT
    channel: str | None = None
    message_draft: str | None = None
    created_at: str | None = None
    user_confirmed_at: str | None = None
    is_demo: bool = True


# ---------------------------------------------------------------------------
# Read models returned by tools
# ---------------------------------------------------------------------------


class WarrantyInfo(BaseModel):
    """Warranty state derived from the dates stored on the asset."""

    status: WarrantyStatus = WarrantyStatus.UNKNOWN
    purchase_date: date | None = None
    warranty_start: date | None = None
    warranty_end: date | None = None
    days_remaining: int | None = None
    expiring_soon_days: int = 30
    source_type: SourceType = SourceType.USER_ENTERED
    verified_by_official_source: bool = False
    basis_note: str = (
        "Based on the dates saved in HomeOps. This is not a verified warranty determination - "
        "check the manufacturer policy and proof of purchase."
    )


class AssetSummary(BaseModel):
    """Compact asset entry for list views."""

    asset_id: str
    name: str
    category: AssetCategory
    location: str | None = None
    brand: str | None = None
    warranty_status: WarrantyStatus = WarrantyStatus.UNKNOWN
    warranty_end: date | None = None
    is_demo: bool = False


class AssetDetail(BaseModel):
    """Full asset record with derived warranty information."""

    asset: Asset
    warranty: WarrantyInfo
    recent_event_ids: list[str] = Field(default_factory=list)
    open_reminder_ids: list[str] = Field(default_factory=list)
    is_demo: bool = False


class MaintenanceEventView(BaseModel):
    """A maintenance event as returned by search results."""

    event_id: str
    asset_id: str | None = None
    asset_name: str | None = None
    event_type: EventType
    description: str
    occurred_at: str | None = None
    created_at: str | None = None
    outcome: str | None = None
    provider_id: str | None = None
    source_type: SourceType = SourceType.USER_ENTERED
    is_demo: bool = False


class ReminderView(BaseModel):
    """A reminder plus its computed due state."""

    reminder_id: str
    asset_id: str | None = None
    asset_name: str | None = None
    title: str
    due_at: str
    timezone: str
    status: ReminderStatus
    is_overdue: bool = False
    minutes_until_due: int | None = None
    recurrence: str | None = None
    source_event_id: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    is_demo: bool = False


class HandoffAction(BaseModel):
    """A single outbound action the user can choose to open."""

    action_type: Literal["maps_search", "whatsapp", "tel", "mailto", "booking_page"]
    label: str
    url: str
    recipient: str | None = None
    message_preview: str | None = None
    requires_user_action: bool = True
    note: str | None = None


class HandoffPayload(BaseModel):
    """Everything the UI needs to review a provider handoff before opening it."""

    issue_event_id: str | None = None
    asset_id: str | None = None
    service_category: ServiceCategory
    locality: str | None = None
    provider: Provider | None = None
    technician_brief: TechnicianBrief | None = None
    actions: list[HandoffAction] = Field(default_factory=list)
    unavailable_actions: list[str] = Field(default_factory=list)
    message_draft: str | None = None
    disclaimer: str = (
        "Opening a link only hands control to an external app. HomeOps does not send messages "
        "or book appointments."
    )


class BriefFact(BaseModel):
    """A single sourced statement inside a technician brief."""

    label: str
    value: str
    record_id: str | None = None
    source_type: SourceType = SourceType.USER_ENTERED
    is_unknown: bool = False


class TechnicianBrief(BaseModel):
    """A record-grounded brief. Every fact points at a stored record."""

    event_id: str | None = None
    asset_id: str | None = None
    title: str
    summary: str
    facts: list[BriefFact] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    related_event_ids: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    summary_provider: Literal["deterministic", "bedrock"] = "deterministic"
    is_demo: bool = False
