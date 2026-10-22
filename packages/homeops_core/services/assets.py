"""Asset inventory queries."""

from __future__ import annotations

import sqlite3

from ..errors import NotFoundError
from ..models import (
    Asset,
    AssetCategory,
    AssetDetail,
    AssetSummary,
    EventType,
    ReminderStatus,
    SourceType,
    WarrantyStatus,
)
from ..timeutil import parse_date, today_in
from .warranty import compute_warranty

MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 20


def _asset_from_row(row: sqlite3.Row) -> Asset:
    return Asset(
        asset_id=row["asset_id"],
        name=row["name"],
        category=AssetCategory(row["category"]),
        location=row["location"],
        brand=row["brand"],
        model=row["model"],
        purchase_date=parse_date(row["purchase_date"], field="purchase_date"),
        warranty_start=parse_date(row["warranty_start"], field="warranty_start"),
        warranty_end=parse_date(row["warranty_end"], field="warranty_end"),
        timezone=row["timezone"],
        manual_ref=row["manual_ref"],
        receipt_ref=row["receipt_ref"],
        source_type=SourceType(row["source_type"]),
        source_ref=row["source_ref"],
        is_demo=bool(row["is_demo"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_assets(
    conn: sqlite3.Connection,
    *,
    query: str | None = None,
    category: AssetCategory | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
    expiring_soon_days: int = 30,
    timezone: str = "Europe/London",
) -> list[AssetSummary]:
    """List household assets with a derived warranty status."""
    limit = max(1, min(int(limit or DEFAULT_LIST_LIMIT), MAX_LIST_LIMIT))
    sql = "SELECT * FROM assets"
    clauses: list[str] = []
    params: list[object] = []

    if category is not None:
        clauses.append("category = ?")
        params.append(str(category))
    if query:
        like = f"%{query.strip()}%"
        clauses.append("(name LIKE ? COLLATE NOCASE OR brand LIKE ? COLLATE NOCASE OR model LIKE ? COLLATE NOCASE OR location LIKE ? COLLATE NOCASE)")
        params.extend([like, like, like, like])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY name COLLATE NOCASE LIMIT ?"
    params.append(limit)

    today = today_in(timezone)
    summaries: list[AssetSummary] = []
    for row in conn.execute(sql, params).fetchall():
        asset = _asset_from_row(row)
        warranty = compute_warranty(
            asset, now_date=today, timezone=timezone, expiring_soon_days=expiring_soon_days
        )
        summaries.append(
            AssetSummary(
                asset_id=asset.asset_id,
                name=asset.name,
                category=asset.category,
                location=asset.location,
                brand=asset.brand,
                warranty_status=warranty.status,
                warranty_end=asset.warranty_end,
                is_demo=asset.is_demo,
            )
        )
    return summaries


def get_asset(
    conn: sqlite3.Connection,
    asset_id: str,
    *,
    expiring_soon_days: int = 30,
    timezone: str = "Europe/London",
    recent_event_limit: int = 10,
) -> Asset:
    """Return the stored asset record."""
    row = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No asset found with id {asset_id!r}", details={"asset_id": asset_id})
    return _asset_from_row(row)


def get_asset_detail(
    conn: sqlite3.Connection,
    asset_id: str,
    *,
    expiring_soon_days: int = 30,
    timezone: str = "Europe/London",
    recent_event_limit: int = 10,
) -> AssetDetail:
    """Return an asset with its warranty state and linked record IDs."""
    asset = get_asset(conn, asset_id, expiring_soon_days=expiring_soon_days, timezone=timezone)
    warranty = compute_warranty(
        asset,
        now_date=today_in(timezone),
        timezone=timezone,
        expiring_soon_days=expiring_soon_days,
    )

    event_rows = conn.execute(
        """
        SELECT event_id FROM maintenance_events
        WHERE asset_id = ?
        ORDER BY COALESCE(occurred_at, created_at) DESC
        LIMIT ?
        """,
        (asset_id, recent_event_limit),
    ).fetchall()
    reminder_rows = conn.execute(
        """
        SELECT reminder_id FROM reminders
        WHERE asset_id = ? AND status NOT IN (?, ?)
        ORDER BY due_at ASC
        LIMIT ?
        """,
        (asset_id, ReminderStatus.COMPLETED.value, ReminderStatus.CANCELLED.value, recent_event_limit),
    ).fetchall()

    return AssetDetail(
        asset=asset,
        warranty=warranty,
        recent_event_ids=[row["event_id"] for row in event_rows],
        open_reminder_ids=[row["reminder_id"] for row in reminder_rows],
        is_demo=asset.is_demo,
    )


def warranty_status_for(conn: sqlite3.Connection, asset_id: str, *, today, timezone: str) -> WarrantyStatus:
    """Small helper used by the orchestrator for quick status checks."""
    asset = get_asset(conn, asset_id, timezone=timezone)
    return compute_warranty(asset, now_date=today, timezone=timezone).status


__all__ = [
    "DEFAULT_LIST_LIMIT",
    "MAX_LIST_LIMIT",
    "EventType",
    "get_asset",
    "get_asset_detail",
    "list_assets",
]
