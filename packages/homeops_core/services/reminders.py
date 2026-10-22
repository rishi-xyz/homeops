"""Reminder lifecycle.

Reminder status is stored, but the *due* state is recomputed from the stored
due time on every read. That keeps a completed reminder from reappearing as
due after a restart and avoids running an always-on scheduler.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import NotFoundError, StateTransitionError, ValidationError
from ..models import Reminder, ReminderStatus, ReminderView, SourceType
from ..timeutil import parse_datetime, utcnow, utcnow_iso

MAX_TITLE_LENGTH = 200
MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 20
TERMINAL_STATUSES = {ReminderStatus.COMPLETED, ReminderStatus.CANCELLED}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _validate_timezone(tz_name: str) -> str:
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(
            f"{tz_name!r} is not a valid IANA timezone", details={"timezone": tz_name}
        ) from exc
    return tz_name


def _reminder_from_row(row: sqlite3.Row) -> Reminder:
    return Reminder(
        reminder_id=row["reminder_id"],
        asset_id=row["asset_id"],
        title=row["title"],
        due_at=row["due_at"],
        timezone=row["timezone"],
        status=ReminderStatus(row["status"]),
        recurrence=row["recurrence"],
        source_event_id=row["source_event_id"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        is_demo=bool(row["is_demo"]),
    )


def effective_status(stored: ReminderStatus, due_at: datetime, now: datetime) -> ReminderStatus:
    """Compute the status a reminder should show right now."""
    if stored in TERMINAL_STATUSES:
        return stored
    if due_at <= now:
        return ReminderStatus.DUE
    if stored is ReminderStatus.SNOOZED:
        return ReminderStatus.SNOOZED
    return ReminderStatus.PENDING


def _to_view(
    reminder: Reminder,
    *,
    asset_name: str | None,
    now: datetime,
) -> ReminderView:
    due = parse_datetime(reminder.due_at, field="due_at") or now
    status = effective_status(reminder.status, due, now)
    delta = due - now
    return ReminderView(
        reminder_id=reminder.reminder_id,
        asset_id=reminder.asset_id,
        asset_name=asset_name,
        title=reminder.title,
        due_at=reminder.due_at,
        timezone=reminder.timezone,
        status=status,
        is_overdue=status is ReminderStatus.DUE,
        minutes_until_due=int(delta.total_seconds() // 60),
        recurrence=reminder.recurrence,
        source_event_id=reminder.source_event_id,
        created_at=reminder.created_at,
        completed_at=reminder.completed_at,
        is_demo=reminder.is_demo,
    )


def create_reminder(
    conn: sqlite3.Connection,
    *,
    title: str,
    due_at: str,
    timezone: str = "Europe/London",
    asset_id: str | None = None,
    source_event_id: str | None = None,
    recurrence: str | None = None,
    is_demo: bool = False,
    source_type: SourceType = SourceType.USER_ENTERED,
) -> ReminderView:
    """Create and persist a reminder."""
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValidationError("Reminder title must not be empty", details={"field": "title"})
    if len(clean_title) > MAX_TITLE_LENGTH:
        raise ValidationError(
            f"Reminder title must be {MAX_TITLE_LENGTH} characters or fewer",
            details={"field": "title", "max_length": MAX_TITLE_LENGTH},
        )

    due = parse_datetime(due_at, field="due_at")
    if due is None:
        raise ValidationError("due_at is required", details={"field": "due_at"})

    tz_name = _validate_timezone((timezone or "Europe/London").strip())

    if asset_id is not None:
        exists = conn.execute("SELECT 1 FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if exists is None:
            raise NotFoundError(f"No asset found with id {asset_id!r}", details={"asset_id": asset_id})

    if source_event_id is not None:
        exists = conn.execute(
            "SELECT 1 FROM maintenance_events WHERE event_id = ?", (source_event_id,)
        ).fetchone()
        if exists is None:
            raise NotFoundError(
                f"No maintenance event found with id {source_event_id!r}",
                details={"source_event_id": source_event_id},
            )

    reminder_id = _new_id("rem")
    now_iso = utcnow_iso()
    conn.execute(
        """
        INSERT INTO reminders (
            reminder_id, asset_id, title, due_at, timezone, status, recurrence,
            source_event_id, created_at, completed_at, is_demo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            reminder_id,
            asset_id,
            clean_title,
            due.isoformat(),
            tz_name,
            ReminderStatus.PENDING.value,
            (recurrence or None),
            source_event_id,
            now_iso,
            1 if is_demo else 0,
        ),
    )
    row = conn.execute("SELECT * FROM reminders WHERE reminder_id = ?", (reminder_id,)).fetchone()
    asset_name = _asset_name(conn, asset_id)
    return _to_view(_reminder_from_row(row), asset_name=asset_name, now=utcnow())


def _asset_name(conn: sqlite3.Connection, asset_id: str | None) -> str | None:
    if not asset_id:
        return None
    row = conn.execute("SELECT name FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
    return row["name"] if row else None


def list_reminders(
    conn: sqlite3.Connection,
    *,
    status: ReminderStatus | None = None,
    asset_id: str | None = None,
    from_at: str | None = None,
    to_at: str | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
) -> list[ReminderView]:
    """List reminders ordered by due time, with the due state recomputed."""
    limit = max(1, min(int(limit or DEFAULT_LIST_LIMIT), MAX_LIST_LIMIT))
    sql = "SELECT * FROM reminders"
    clauses: list[str] = []
    params: list[object] = []

    if asset_id is not None:
        clauses.append("asset_id = ?")
        params.append(asset_id)
    if from_at is not None:
        start = parse_datetime(from_at, field="from_at")
        if start is None:
            raise ValidationError("from_at must be an ISO-8601 timestamp", details={"field": "from_at"})
        clauses.append("due_at >= ?")
        params.append(start.isoformat())
    if to_at is not None:
        end = parse_datetime(to_at, field="to_at")
        if end is None:
            raise ValidationError("to_at must be an ISO-8601 timestamp", details={"field": "to_at"})
        clauses.append("due_at <= ?")
        params.append(end.isoformat())
    if status is not None:
        if status in TERMINAL_STATUSES:
            clauses.append("status = ?")
            params.append(status.value)
        else:
            # "pending"/"due"/"snoozed" are computed, so filter after loading.
            pass

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY due_at ASC LIMIT ?"
    params.append(limit)

    now = utcnow()
    views: list[ReminderView] = []
    for row in conn.execute(sql, params).fetchall():
        reminder = _reminder_from_row(row)
        view = _to_view(reminder, asset_name=_asset_name(conn, reminder.asset_id), now=now)
        if status is not None and status not in TERMINAL_STATUSES and view.status is not status:
            continue
        views.append(view)
    return views


def get_reminder(conn: sqlite3.Connection, reminder_id: str) -> Reminder:
    row = conn.execute("SELECT * FROM reminders WHERE reminder_id = ?", (reminder_id,)).fetchone()
    if row is None:
        raise NotFoundError(
            f"No reminder found with id {reminder_id!r}", details={"reminder_id": reminder_id}
        )
    return _reminder_from_row(row)


def complete_reminder(conn: sqlite3.Connection, reminder_id: str) -> ReminderView:
    """Mark a reminder complete. Completing an already completed reminder is a no-op."""
    reminder = get_reminder(conn, reminder_id)
    if reminder.status is ReminderStatus.COMPLETED:
        return _to_view(reminder, asset_name=_asset_name(conn, reminder.asset_id), now=utcnow())
    if reminder.status is ReminderStatus.CANCELLED:
        raise StateTransitionError(
            "This reminder was cancelled and cannot be completed",
            details={"reminder_id": reminder_id, "status": reminder.status.value},
        )
    conn.execute(
        "UPDATE reminders SET status = ?, completed_at = ? WHERE reminder_id = ?",
        (ReminderStatus.COMPLETED.value, utcnow_iso(), reminder_id),
    )
    updated = get_reminder(conn, reminder_id)
    return _to_view(updated, asset_name=_asset_name(conn, updated.asset_id), now=utcnow())


def snooze_reminder(
    conn: sqlite3.Connection, reminder_id: str, *, due_at: str, timezone: str | None = None
) -> ReminderView:
    """Postpone a reminder to a new due time."""
    reminder = get_reminder(conn, reminder_id)
    if reminder.status is ReminderStatus.COMPLETED:
        raise StateTransitionError(
            "A completed reminder cannot be snoozed",
            details={"reminder_id": reminder_id, "status": reminder.status.value},
        )
    new_due = parse_datetime(due_at, field="due_at")
    if new_due is None:
        raise ValidationError("due_at is required", details={"field": "due_at"})
    tz_name = _validate_timezone(timezone or reminder.timezone)
    conn.execute(
        "UPDATE reminders SET due_at = ?, timezone = ?, status = ?, completed_at = NULL WHERE reminder_id = ?",
        (new_due.isoformat(), tz_name, ReminderStatus.SNOOZED.value, reminder_id),
    )
    updated = get_reminder(conn, reminder_id)
    return _to_view(updated, asset_name=_asset_name(conn, updated.asset_id), now=utcnow())


def cancel_reminder(conn: sqlite3.Connection, reminder_id: str) -> ReminderView:
    """Cancel a reminder."""
    reminder = get_reminder(conn, reminder_id)
    if reminder.status is ReminderStatus.CANCELLED:
        return _to_view(reminder, asset_name=_asset_name(conn, reminder.asset_id), now=utcnow())
    conn.execute(
        "UPDATE reminders SET status = ? WHERE reminder_id = ?",
        (ReminderStatus.CANCELLED.value, reminder_id),
    )
    updated = get_reminder(conn, reminder_id)
    return _to_view(updated, asset_name=_asset_name(conn, updated.asset_id), now=utcnow())


def default_due_at(days: int = 30) -> str:
    """Helper used by the CLI and seed data."""
    return (utcnow() + timedelta(days=days)).isoformat()
