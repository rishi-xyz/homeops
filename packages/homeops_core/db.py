"""SQLite access layer.

HomeOps stores everything in a single local SQLite file. Connections are
opened per unit of work and closed afterwards, which keeps the layer safe to
use from FastAPI's thread pool without extra locking.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from .config import Settings, get_settings

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS assets (
        asset_id        TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        category        TEXT NOT NULL,
        location        TEXT,
        brand           TEXT,
        model           TEXT,
        purchase_date   TEXT,
        warranty_start  TEXT,
        warranty_end    TEXT,
        timezone        TEXT NOT NULL,
        manual_ref      TEXT,
        receipt_ref     TEXT,
        source_type     TEXT NOT NULL,
        source_ref      TEXT,
        is_demo         INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS maintenance_events (
        event_id     TEXT PRIMARY KEY,
        asset_id     TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
        event_type   TEXT NOT NULL,
        description  TEXT NOT NULL,
        occurred_at  TEXT,
        created_at   TEXT NOT NULL,
        outcome      TEXT,
        provider_id  TEXT,
        location     TEXT,
        source_type  TEXT NOT NULL,
        source_ref   TEXT,
        is_demo      INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reminders (
        reminder_id     TEXT PRIMARY KEY,
        asset_id        TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
        title           TEXT NOT NULL,
        due_at          TEXT NOT NULL,
        timezone        TEXT NOT NULL,
        status          TEXT NOT NULL,
        recurrence      TEXT,
        source_event_id TEXT,
        created_at      TEXT NOT NULL,
        completed_at    TEXT,
        is_demo         INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS providers (
        provider_id       TEXT PRIMARY KEY,
        name              TEXT NOT NULL,
        service_categories TEXT NOT NULL,
        phone             TEXT,
        email             TEXT,
        booking_url       TEXT,
        locality          TEXT,
        source_type       TEXT NOT NULL,
        source_ref        TEXT,
        is_demo           INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS service_slots (
        slot_id     TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL REFERENCES providers(provider_id) ON DELETE CASCADE,
        service_type TEXT NOT NULL,
        starts_at   TEXT NOT NULL,
        ends_at     TEXT NOT NULL,
        status      TEXT NOT NULL,
        is_demo     INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS service_requests (
        request_id       TEXT PRIMARY KEY,
        event_id         TEXT,
        provider_id      TEXT,
        slot_id          TEXT,
        status           TEXT NOT NULL,
        channel          TEXT,
        message_draft    TEXT,
        confirmation_token TEXT,
        created_at       TEXT NOT NULL,
        user_confirmed_at TEXT,
        is_demo          INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tool_audit_events (
        audit_id      TEXT PRIMARY KEY,
        tool_name     TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        result_status TEXT NOT NULL,
        duration_ms   INTEGER,
        record_ids    TEXT,
        short_summary TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_asset ON maintenance_events(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_occurred ON maintenance_events(occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at)",
    "CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status)",
    "CREATE INDEX IF NOT EXISTS idx_slots_provider ON service_slots(provider_id)",
)


def connect(settings: Settings | None = None, *, path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with the HomeOps pragmas applied."""
    settings = settings or get_settings()
    db_path = path or settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def session(settings: Settings | None = None, *, path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Transactional connection: commits on success, rolls back on error."""
    conn = connect(settings, path=path)
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        with suppress(sqlite3.Error):  # pragma: no cover - connection already broken
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    """Create every table and index if it does not exist yet."""
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)


def reset_database(settings: Settings | None = None) -> None:
    """Delete the local database file so it can be recreated from seed."""
    settings = settings or get_settings()
    db_path = settings.db_path
    for candidate in (db_path, db_path.with_suffix(db_path.suffix + "-wal"), db_path.with_suffix(db_path.suffix + "-shm")):
        if candidate.exists():
            candidate.unlink()
    settings.ensure_directories()


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert sqlite rows into plain dictionaries."""
    return [dict(row) for row in rows]
