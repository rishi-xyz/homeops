"""Seed loader for the fictional demo household.

The seed is fully deterministic: every record is invented, marked ``is_demo``
and carries a ``demo_seed`` source. Dates that must stay meaningful over time
(reminder due dates, appointment slots) are stored as offsets relative to the
day the database is seeded.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import db
from .config import Settings, get_settings
from .timeutil import iso, utcnow, utcnow_iso

SEED_FILENAME = "household.json"


class SeedError(RuntimeError):
    """Raised when the seed file is missing or malformed."""


def seed_file_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.seed_dir / SEED_FILENAME


def load_seed(settings: Settings | None = None) -> dict:
    """Read and validate the seed file."""
    settings = settings or get_settings()
    path = seed_file_path(settings)
    if not path.is_file():
        raise SeedError(f"Seed file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SeedError(f"Seed file {path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SeedError(f"Seed file {path} must contain a JSON object")
    for key in ("assets", "providers", "maintenance_events", "reminders", "service_slots"):
        if not isinstance(payload.get(key), list):
            raise SeedError(f"Seed file {path} is missing the '{key}' list")
    return payload


def _seed_datetime(day_offset: int, clock: str | None, tz_name: str) -> datetime:
    """Build an aware datetime ``day_offset`` days from today at ``clock``."""
    zone = ZoneInfo(tz_name)
    day = date.today() + timedelta(days=day_offset)
    hh, mm = (clock or "09:00").split(":")
    return datetime.combine(day, time(int(hh), int(mm)), tzinfo=zone)


def _seed_date(day_offset: int | None, absolute: str | None) -> str | None:
    """Resolve a seed date that may be absolute or relative to the seed day.

    Relative offsets keep the demo meaningful whenever the seed is rebuilt:
    ``-20`` is twenty days ago, ``24`` is twenty-four days from now.
    """
    if day_offset is not None:
        return (date.today() + timedelta(days=int(day_offset))).isoformat()
    return absolute


def seed_database(settings: Settings | None = None, *, reset: bool = True) -> dict[str, int]:
    """(Re)create the local database and load the fictional demo records."""
    settings = settings or get_settings()
    payload = load_seed(settings)
    tz_name = settings.household_timezone

    if reset:
        db.reset_database(settings)
    settings.ensure_directories()

    counts = {"assets": 0, "providers": 0, "maintenance_events": 0, "reminders": 0, "service_slots": 0}
    now_iso = utcnow_iso()

    with db.session(settings) as conn:
        db.init_schema(conn)

        for asset in payload["assets"]:
            conn.execute(
                """
                INSERT INTO assets (
                    asset_id, name, category, location, brand, model, purchase_date,
                    warranty_start, warranty_end, timezone, manual_ref, receipt_ref,
                    source_type, source_ref, is_demo, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset["asset_id"],
                    asset["name"],
                    asset["category"],
                    asset.get("location"),
                    asset.get("brand"),
                    asset.get("model"),
                    _seed_date(asset.get("purchase_in_days"), asset.get("purchase_date")),
                    _seed_date(asset.get("warranty_start_in_days"), asset.get("warranty_start")),
                    _seed_date(asset.get("warranty_end_in_days"), asset.get("warranty_end")),
                    asset.get("timezone", tz_name),
                    asset.get("manual_ref"),
                    asset.get("receipt_ref"),
                    asset.get("source_type", "demo_seed"),
                    asset.get("source_ref"),
                    1 if asset.get("is_demo", True) else 0,
                    now_iso,
                    now_iso,
                ),
            )
            counts["assets"] += 1

        for provider in payload["providers"]:
            conn.execute(
                """
                INSERT INTO providers (
                    provider_id, name, service_categories, phone, email, booking_url,
                    locality, source_type, source_ref, is_demo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider["provider_id"],
                    provider["name"],
                    json.dumps(provider.get("service_categories", [])),
                    provider.get("phone"),
                    provider.get("email"),
                    provider.get("booking_url"),
                    provider.get("locality"),
                    provider.get("source_type", "demo_seed"),
                    provider.get("source_ref"),
                    1 if provider.get("is_demo", True) else 0,
                ),
            )
            counts["providers"] += 1

        for event in payload["maintenance_events"]:
            conn.execute(
                """
                INSERT INTO maintenance_events (
                    event_id, asset_id, event_type, description, occurred_at, created_at,
                    outcome, provider_id, location, source_type, source_ref, is_demo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event.get("asset_id"),
                    event["event_type"],
                    event["description"],
                    event.get("occurred_at"),
                    event.get("created_at") or now_iso,
                    event.get("outcome"),
                    event.get("provider_id"),
                    event.get("location"),
                    event.get("source_type", "demo_seed"),
                    event.get("source_ref"),
                    1 if event.get("is_demo", True) else 0,
                ),
            )
            counts["maintenance_events"] += 1

        for reminder in payload["reminders"]:
            due = _seed_datetime(int(reminder.get("due_in_days", 0)), reminder.get("due_time"), tz_name)
            completed_at = None
            status = reminder.get("status", "pending")
            if status == "completed":
                completed_at = iso(due)
            conn.execute(
                """
                INSERT INTO reminders (
                    reminder_id, asset_id, title, due_at, timezone, status, recurrence,
                    source_event_id, created_at, completed_at, is_demo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reminder["reminder_id"],
                    reminder.get("asset_id"),
                    reminder["title"],
                    iso(due),
                    reminder.get("timezone", tz_name),
                    status,
                    reminder.get("recurrence"),
                    reminder.get("source_event_id"),
                    now_iso,
                    completed_at,
                    1 if reminder.get("is_demo", True) else 0,
                ),
            )
            counts["reminders"] += 1

        for slot in payload["service_slots"]:
            starts = _seed_datetime(int(slot.get("starts_in_days", 0)), slot.get("start_time"), tz_name)
            ends = starts + timedelta(minutes=int(slot.get("duration_minutes", 60)))
            conn.execute(
                """
                INSERT INTO service_slots (
                    slot_id, provider_id, service_type, starts_at, ends_at, status, is_demo
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slot["slot_id"],
                    slot["provider_id"],
                    slot["service_type"],
                    iso(starts),
                    iso(ends),
                    slot.get("status", "available"),
                    1 if slot.get("is_demo", True) else 0,
                ),
            )
            counts["service_slots"] += 1

        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('seed_version', ?)",
            (str(payload.get("seed_version", "unknown")),),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('seeded_at', ?)",
            (utcnow_iso(),),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('demo_mode', ?)",
            ("true" if settings.demo_mode else "false",),
        )

    return counts


def database_status(settings: Settings | None = None) -> dict[str, object]:
    """Summarise what is currently stored in the local database."""
    settings = settings or get_settings()
    status: dict[str, object] = {
        "database": str(settings.db_path),
        "exists": settings.db_path.exists(),
        "seeded_at": None,
        "seed_version": None,
        "counts": {},
    }
    if not settings.db_path.exists():
        return status

    with db.session(settings) as conn:
        db.init_schema(conn)
        for table in ("assets", "providers", "maintenance_events", "reminders", "service_slots", "service_requests"):
            row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
            status["counts"][table] = row["total"]  # type: ignore[index]
        for key in ("seeded_at", "seed_version"):
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            status[key] = row["value"] if row else None

    return status


def seed_summary(settings: Settings | None = None) -> str:
    """One line summary used by the CLI."""
    status = database_status(settings)
    counts = status.get("counts", {})  # type: ignore[assignment]
    parts = ", ".join(f"{name}={count}" for name, count in counts.items())  # type: ignore[union-attr]
    return f"{status['database']} | seeded_at={status['seeded_at']} | {parts}"


__all__ = [
    "SEED_FILENAME",
    "SeedError",
    "database_status",
    "load_seed",
    "seed_database",
    "seed_summary",
    "utcnow",
]
