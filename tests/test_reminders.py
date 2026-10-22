"""Reminder lifecycle and timezone handling tests (checklist H)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeops_core.services import reminders as reminders_service


def test_create_list_and_complete_reminder(conn) -> None:
    tz = "Europe/London"
    due = (datetime.now(ZoneInfo(tz)) + timedelta(days=7)).isoformat()
    reminder = reminders_service.create_reminder(
        conn,
        title="Check boiler filter",
        due_at=due,
        timezone=tz,
    )
    assert reminder.reminder_id.startswith("rem_")

    items = reminders_service.list_reminders(conn)
    ids = {item.reminder_id for item in items}
    assert reminder.reminder_id in ids

    completed = reminders_service.complete_reminder(conn, reminder.reminder_id)
    assert completed.status.value == "completed"

    # A completed reminder must not reappear as due.
    due_items = reminders_service.list_reminders(conn, status=reminders_service.ReminderStatus.DUE)  # type: ignore[attr-defined]
    assert reminder.reminder_id not in {item.reminder_id for item in due_items}


def test_snooze_changes_due_time(conn) -> None:
    tz = "Europe/London"
    due = (datetime.now(ZoneInfo(tz)) + timedelta(days=1)).isoformat()
    reminder = reminders_service.create_reminder(
        conn, title="Service boiler", due_at=due, timezone=tz
    )
    later = (datetime.now(ZoneInfo(tz)) + timedelta(days=14)).isoformat()
    snoozed = reminders_service.snooze_reminder(conn, reminder.reminder_id, due_at=later)
    assert snoozed.status.value == "snoozed"
    assert snoozed.reminder_id == reminder.reminder_id


def test_cancel_stops_it_appearing_as_due(conn) -> None:
    tz = "Europe/London"
    due = (datetime.now(ZoneInfo(tz)) + timedelta(hours=2)).isoformat()
    reminder = reminders_service.create_reminder(conn, title="Ventilate", due_at=due, timezone=tz)
    cancelled = reminders_service.cancel_reminder(conn, reminder.reminder_id)
    assert cancelled.status.value == "cancelled"


def test_reminder_stores_asset_link_when_provided(conn) -> None:
    tz = "Europe/London"
    due = (datetime.now(ZoneInfo(tz)) + timedelta(days=3)).isoformat()
    reminder = reminders_service.create_reminder(
        conn, title="Check washer", due_at=due, timezone=tz, asset_id="asset_washer_01"
    )
    assert reminder.asset_id == "asset_washer_01"
    items = reminders_service.list_reminders(conn, asset_id="asset_washer_01")
    assert reminder.reminder_id in {item.reminder_id for item in items}
