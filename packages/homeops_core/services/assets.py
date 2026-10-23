"""Asset inventory queries and creation."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import NotFoundError, ValidationError
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
from ..timeutil import parse_date, today_in, utcnow_iso
from .warranty import compute_warranty

MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 20
MAX_NAME_LENGTH = 200
MAX_TEXT_LENGTH = 200


def _new_asset_id() -> str:
    return f"asset_{uuid.uuid4().hex[:12]}"


def _optional_text(value: str | None, field: str) -> str | None:
    """Trim an optional free-text field; empty input stays unknown."""
    if value is None:
        return None
    clean = str(value).strip()
    if not clean:
        return None
    if len(clean) > MAX_TEXT_LENGTH:
        raise ValidationError(
            f"{field} must be {MAX_TEXT_LENGTH} characters or fewer",
            details={"field": field, "max_length": MAX_TEXT_LENGTH},
        )
    return clean


def _validate_timezone(tz_name: str) -> str:
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(
            f"{tz_name!r} is not a valid IANA timezone", details={"timezone": tz_name}
        ) from exc
    return tz_name


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


def create_asset(
    conn: sqlite3.Connection,
    *,
    name: str,
    category: AssetCategory | str = AssetCategory.APPLIANCE,
    location: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    purchase_date: str | date | None = None,
    warranty_start: str | date | None = None,
    warranty_end: str | date | None = None,
    timezone: str = "Europe/London",
    manual_ref: str | None = None,
    receipt_ref: str | None = None,
    source_type: SourceType | str = SourceType.USER_ENTERED,
    source_ref: str | None = None,
    is_demo: bool = False,
) -> Asset:
    """Create a household asset.

    Only details supplied by the caller are stored. Purchase and warranty dates
    that were not supplied stay unknown - no term is inferred from a purchase
    date, and a missing warranty end never becomes a guess.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError("Asset name must not be empty", details={"field": "name"})
    if len(clean_name) > MAX_NAME_LENGTH:
        raise ValidationError(
            f"Asset name must be {MAX_NAME_LENGTH} characters or fewer",
            details={"field": "name", "max_length": MAX_NAME_LENGTH},
        )

    try:
        asset_category = category if isinstance(category, AssetCategory) else AssetCategory(str(category))
    except ValueError as exc:
        raise ValidationError(
            f"{category!r} is not a valid asset category",
            details={"field": "category", "allowed": [item.value for item in AssetCategory]},
        ) from exc

    try:
        asset_source = source_type if isinstance(source_type, SourceType) else SourceType(str(source_type))
    except ValueError as exc:
        raise ValidationError(
            f"{source_type!r} is not a valid source type",
            details={"field": "source_type", "allowed": [item.value for item in SourceType]},
        ) from exc

    zone = _validate_timezone(timezone or "Europe/London")
    purchase = parse_date(purchase_date, field="purchase_date")
    start = parse_date(warranty_start, field="warranty_start")
    end = parse_date(warranty_end, field="warranty_end")
    if start is not None and end is not None and start > end:
        raise ValidationError(
            "warranty_start must not be after warranty_end",
            details={"field": "warranty_start"},
        )

    asset_id = _new_asset_id()
    now = utcnow_iso()
    conn.execute(
        """
        INSERT INTO assets (
            asset_id, name, category, location, brand, model, purchase_date,
            warranty_start, warranty_end, timezone, manual_ref, receipt_ref,
            source_type, source_ref, is_demo, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            clean_name,
            str(asset_category),
            _optional_text(location, "location"),
            _optional_text(brand, "brand"),
            _optional_text(model, "model"),
            purchase.isoformat() if purchase else None,
            start.isoformat() if start else None,
            end.isoformat() if end else None,
            zone,
            _optional_text(manual_ref, "manual_ref"),
            _optional_text(receipt_ref, "receipt_ref"),
            str(asset_source),
            _optional_text(source_ref, "source_ref"),
            1 if is_demo else 0,
            now,
            now,
        ),
    )
    row = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
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
    "create_asset",
    "get_asset",
    "get_asset_detail",
    "list_assets",
]
