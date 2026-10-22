"""Simulated service slots and demo service requests.

Everything in this module is a *simulation*. Slots are fictional, requests are
local records, and the strongest status a request can reach is
``confirmed_demo``. No real provider is ever contacted.
"""

from __future__ import annotations

import secrets
import sqlite3

from ..errors import NotFoundError, StateTransitionError, ValidationError
from ..models import RequestStatus, ServiceCategory, ServiceRequest, ServiceSlot
from ..timeutil import parse_date, parse_datetime, utcnow_iso

MAX_SLOT_LIMIT = 20
DEFAULT_SLOT_LIMIT = 10
CONFIRMABLE_STATUSES = {
    RequestStatus.AWAITING_USER_ACTION,
    RequestStatus.HANDOFF_OPENED,
    RequestStatus.DRAFT,
}


def _slot_from_row(row: sqlite3.Row) -> ServiceSlot:
    return ServiceSlot(
        slot_id=row["slot_id"],
        provider_id=row["provider_id"],
        service_type=ServiceCategory(row["service_type"]),
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        status=row["status"],
        is_demo=bool(row["is_demo"]),
    )


def _request_from_row(row: sqlite3.Row) -> ServiceRequest:
    return ServiceRequest(
        request_id=row["request_id"],
        event_id=row["event_id"],
        provider_id=row["provider_id"],
        slot_id=row["slot_id"],
        status=RequestStatus(row["status"]),
        channel=row["channel"],
        message_draft=row["message_draft"],
        created_at=row["created_at"],
        user_confirmed_at=row["user_confirmed_at"],
        is_demo=bool(row["is_demo"]),
    )


def list_demo_slots(
    conn: sqlite3.Connection,
    *,
    service_type: ServiceCategory,
    preferred_date=None,
    limit: int = DEFAULT_SLOT_LIMIT,
) -> list[ServiceSlot]:
    """List fictional appointment slots. An empty result is valid."""
    limit = max(1, min(int(limit or DEFAULT_SLOT_LIMIT), MAX_SLOT_LIMIT))
    sql = "SELECT * FROM service_slots WHERE service_type = ? AND status = 'available'"
    params: list[object] = [str(service_type)]

    if preferred_date is not None:
        day = parse_date(preferred_date, field="preferred_date")
        if day is None:
            raise ValidationError(
                "preferred_date must be an ISO-8601 date", details={"field": "preferred_date"}
            )
        sql += " AND DATE(starts_at) = ?"
        params.append(day.isoformat())

    sql += " ORDER BY starts_at ASC LIMIT ?"
    params.append(limit)
    return [_slot_from_row(row) for row in conn.execute(sql, params).fetchall()]


def get_slot(conn: sqlite3.Connection, slot_id: str) -> ServiceSlot:
    row = conn.execute("SELECT * FROM service_slots WHERE slot_id = ?", (slot_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No service slot found with id {slot_id!r}", details={"slot_id": slot_id})
    return _slot_from_row(row)


def draft_service_request(
    conn: sqlite3.Connection,
    *,
    slot_id: str,
    event_id: str | None = None,
    note: str | None = None,
    provider_id: str | None = None,
) -> tuple[ServiceRequest, str]:
    """Create a pending demo request.

    Returns the request and a single-use confirmation token. The request stays
    ``awaiting_user_action`` until the user explicitly confirms it.
    """
    slot = get_slot(conn, slot_id)
    if slot.status != "available":
        raise StateTransitionError(
            f"Slot {slot_id!r} is not available (status {slot.status})",
            details={"slot_id": slot_id, "status": slot.status},
        )

    if event_id is not None:
        exists = conn.execute(
            "SELECT 1 FROM maintenance_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if exists is None:
            raise NotFoundError(
                f"No maintenance event found with id {event_id!r}", details={"event_id": event_id}
            )

    request_id = f"req_{secrets.token_hex(8)}"
    token = secrets.token_urlsafe(24)
    now_iso = utcnow_iso()
    conn.execute(
        """
        INSERT INTO service_requests (
            request_id, event_id, provider_id, slot_id, status, channel,
            message_draft, confirmation_token, created_at, user_confirmed_at, is_demo
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, 1)
        """,
        (
            request_id,
            event_id,
            provider_id or slot.provider_id,
            slot_id,
            RequestStatus.AWAITING_USER_ACTION.value,
            (note or None),
            token,
            now_iso,
        ),
    )
    row = conn.execute("SELECT * FROM service_requests WHERE request_id = ?", (request_id,)).fetchone()
    return _request_from_row(row), token


def get_request(conn: sqlite3.Connection, request_id: str) -> ServiceRequest:
    row = conn.execute("SELECT * FROM service_requests WHERE request_id = ?", (request_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No service request found with id {request_id!r}", details={"request_id": request_id})
    return _request_from_row(row)


def confirm_service_request(
    conn: sqlite3.Connection, *, request_id: str, confirmation_token: str
) -> ServiceRequest:
    """Confirm a pending demo request.

    The caller must present the token issued when the request was drafted, so
    a request cannot be confirmed by accident. Confirming twice is a no-op.
    """
    row = conn.execute("SELECT * FROM service_requests WHERE request_id = ?", (request_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No service request found with id {request_id!r}", details={"request_id": request_id})

    request = _request_from_row(row)

    if request.status is RequestStatus.CONFIRMED_DEMO:
        return request  # idempotent

    if request.status not in CONFIRMABLE_STATUSES:
        raise StateTransitionError(
            f"Request is {request.status.value} and cannot be confirmed",
            details={"request_id": request_id, "status": request.status.value},
        )

    stored_token = row["confirmation_token"]
    if not confirmation_token or not stored_token:
        raise StateTransitionError(
            "This request needs an explicit confirmation before it can be confirmed",
            details={"request_id": request_id, "status": request.status.value},
        )
    if not secrets.compare_digest(str(stored_token), str(confirmation_token)):
        raise StateTransitionError(
            "Confirmation reference did not match this request",
            details={"request_id": request_id},
        )

    conn.execute(
        """
        UPDATE service_requests
        SET status = ?, user_confirmed_at = ?
        WHERE request_id = ?
        """,
        (RequestStatus.CONFIRMED_DEMO.value, utcnow_iso(), request_id),
    )
    return get_request(conn, request_id)


def list_requests(conn: sqlite3.Connection, *, limit: int = 20) -> list[ServiceRequest]:
    limit = max(1, min(int(limit or 20), 100))
    rows = conn.execute(
        "SELECT * FROM service_requests ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_request_from_row(row) for row in rows]


def slot_is_in_future(slot: ServiceSlot) -> bool:
    """True when the slot start time is still ahead of now."""
    starts = parse_datetime(slot.starts_at, field="starts_at")
    if starts is None:
        return False
    from ..timeutil import utcnow

    return starts > utcnow()
