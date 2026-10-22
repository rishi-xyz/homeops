"""Maintenance history: logging new events and searching past ones."""

from __future__ import annotations

import sqlite3
import uuid

from ..errors import NotFoundError, ValidationError
from ..models import EventType, MaintenanceEvent, MaintenanceEventView, SourceType
from ..timeutil import parse_datetime, utcnow_iso

MAX_DESCRIPTION_LENGTH = 2000
MAX_OUTCOME_LENGTH = 1000
MAX_SEARCH_LIMIT = 50
DEFAULT_SEARCH_LIMIT = 10
MAX_QUERY_LENGTH = 200


def _new_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _event_from_row(row: sqlite3.Row) -> MaintenanceEvent:
    return MaintenanceEvent(
        event_id=row["event_id"],
        asset_id=row["asset_id"],
        event_type=EventType(row["event_type"]),
        description=row["description"],
        occurred_at=row["occurred_at"],
        created_at=row["created_at"],
        outcome=row["outcome"],
        provider_id=row["provider_id"],
        location=row["location"],
        source_type=SourceType(row["source_type"]),
        source_ref=row["source_ref"],
        is_demo=bool(row["is_demo"]),
    )


def _view_from_row(row: sqlite3.Row) -> MaintenanceEventView:
    return MaintenanceEventView(
        event_id=row["event_id"],
        asset_id=row["asset_id"],
        # sqlite3.Row has no .get(); an absent column means "not selected".
        asset_name=row["asset_name"] if "asset_name" in row else None,  # noqa: SIM401
        event_type=EventType(row["event_type"]),
        description=row["description"],
        occurred_at=row["occurred_at"],
        created_at=row["created_at"],
        outcome=row["outcome"],
        provider_id=row["provider_id"],
        source_type=SourceType(row["source_type"]),
        is_demo=bool(row["is_demo"]),
    )


def log_maintenance_event(
    conn: sqlite3.Connection,
    *,
    event_type: EventType,
    description: str,
    asset_id: str | None = None,
    occurred_at: str | None = None,
    outcome: str | None = None,
    location: str | None = None,
    provider_id: str | None = None,
    source_type: SourceType = SourceType.USER_ENTERED,
    source_ref: str | None = None,
    is_demo: bool = False,
) -> MaintenanceEventView:
    """Record a new maintenance event."""
    clean_description = (description or "").strip()
    if not clean_description:
        raise ValidationError("description must not be empty", details={"field": "description"})
    if len(clean_description) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(
            f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer",
            details={"field": "description", "max_length": MAX_DESCRIPTION_LENGTH},
        )
    if outcome and len(outcome) > MAX_OUTCOME_LENGTH:
        raise ValidationError(
            f"outcome must be {MAX_OUTCOME_LENGTH} characters or fewer",
            details={"field": "outcome", "max_length": MAX_OUTCOME_LENGTH},
        )

    if asset_id is not None:
        exists = conn.execute("SELECT 1 FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if exists is None:
            raise NotFoundError(f"No asset found with id {asset_id!r}", details={"asset_id": asset_id})

    if provider_id is not None:
        exists = conn.execute("SELECT 1 FROM providers WHERE provider_id = ?", (provider_id,)).fetchone()
        if exists is None:
            raise NotFoundError(
                f"No provider found with id {provider_id!r}", details={"provider_id": provider_id}
            )

    occurred = parse_datetime(occurred_at, field="occurred_at") if occurred_at else None
    event_id = _new_id()
    conn.execute(
        """
        INSERT INTO maintenance_events (
            event_id, asset_id, event_type, description, occurred_at, created_at,
            outcome, provider_id, location, source_type, source_ref, is_demo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            asset_id,
            str(event_type),
            clean_description,
            occurred.isoformat() if occurred else None,
            utcnow_iso(),
            (outcome or None),
            provider_id,
            (location or None),
            str(source_type),
            (source_ref or None),
            1 if is_demo else 0,
        ),
    )
    row = conn.execute(
        """
        SELECT e.*, a.name AS asset_name
        FROM maintenance_events e
        LEFT JOIN assets a ON a.asset_id = e.asset_id
        WHERE e.event_id = ?
        """,
        (event_id,),
    ).fetchone()
    return _view_from_row(row)


def search_maintenance_history(
    conn: sqlite3.Connection,
    *,
    asset_id: str | None = None,
    event_type: EventType | None = None,
    query: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[MaintenanceEventView]:
    """Search maintenance history. An empty result is a valid answer."""
    limit = max(1, min(int(limit or DEFAULT_SEARCH_LIMIT), MAX_SEARCH_LIMIT))
    if query and len(query) > MAX_QUERY_LENGTH:
        raise ValidationError(
            f"query must be {MAX_QUERY_LENGTH} characters or fewer",
            details={"field": "query", "max_length": MAX_QUERY_LENGTH},
        )

    sql = """
        SELECT e.*, a.name AS asset_name
        FROM maintenance_events e
        LEFT JOIN assets a ON a.asset_id = e.asset_id
    """
    clauses: list[str] = []
    params: list[object] = []

    if asset_id is not None:
        clauses.append("e.asset_id = ?")
        params.append(asset_id)
    if event_type is not None:
        clauses.append("e.event_type = ?")
        params.append(str(event_type))
    if query:
        like = f"%{query.strip()}%"
        clauses.append(
            "(e.description LIKE ? COLLATE NOCASE OR e.outcome LIKE ? COLLATE NOCASE OR a.name LIKE ? COLLATE NOCASE)"
        )
        params.extend([like, like, like])
    if start_at is not None:
        start = parse_datetime(start_at, field="start_at")
        if start is None:
            raise ValidationError("start_at must be an ISO-8601 timestamp", details={"field": "start_at"})
        clauses.append("COALESCE(e.occurred_at, e.created_at) >= ?")
        params.append(start.isoformat())
    if end_at is not None:
        end = parse_datetime(end_at, field="end_at")
        if end is None:
            raise ValidationError("end_at must be an ISO-8601 timestamp", details={"field": "end_at"})
        clauses.append("COALESCE(e.occurred_at, e.created_at) <= ?")
        params.append(end.isoformat())

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY COALESCE(e.occurred_at, e.created_at) DESC LIMIT ?"
    params.append(limit)

    return [_view_from_row(row) for row in conn.execute(sql, params).fetchall()]


def get_event(conn: sqlite3.Connection, event_id: str) -> MaintenanceEvent:
    row = conn.execute("SELECT * FROM maintenance_events WHERE event_id = ?", (event_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No maintenance event found with id {event_id!r}", details={"event_id": event_id})
    return _event_from_row(row)


def events_for_asset(conn: sqlite3.Connection, asset_id: str, *, limit: int = 10) -> list[MaintenanceEventView]:
    """Recent events for one asset, newest first."""
    rows = conn.execute(
        """
        SELECT e.*, a.name AS asset_name
        FROM maintenance_events e
        LEFT JOIN assets a ON a.asset_id = e.asset_id
        WHERE e.asset_id = ?
        ORDER BY COALESCE(e.occurred_at, e.created_at) DESC
        LIMIT ?
        """,
        (asset_id, max(1, min(limit, MAX_SEARCH_LIMIT))),
    ).fetchall()
    return [_view_from_row(row) for row in rows]
