"""Technician brief assembly.

The brief is assembled from stored records only. Every statement carries the
record it came from, and anything HomeOps does not know is listed as an
explicit unknown rather than being guessed or generated.
"""

from __future__ import annotations

import sqlite3

from ..errors import ValidationError
from ..models import BriefFact, ServiceCategory, TechnicianBrief
from ..timeutil import parse_datetime
from . import maintenance as maintenance_service
from . import warranty as warranty_service
from .assets import get_asset


def _unknown(label: str) -> BriefFact:
    return BriefFact(label=label, value="Not recorded in HomeOps", is_unknown=True)


def build_technician_brief(
    conn: sqlite3.Connection,
    *,
    event_id: str | None = None,
    asset_id: str | None = None,
    include_history: bool = True,
    expiring_soon_days: int = 30,
    timezone: str = "Europe/London",
    max_history: int = 5,
) -> TechnicianBrief:
    """Build a record-grounded brief for an issue or an asset."""
    if event_id is None and asset_id is None:
        raise ValidationError(
            "Provide event_id or asset_id so the brief can be grounded in records",
            details={"fields": ["event_id", "asset_id"]},
        )

    event = None
    if event_id is not None:
        event = maintenance_service.get_event(conn, event_id)
        asset_id = asset_id or event.asset_id

    if asset_id is None:
        raise ValidationError(
            "This event is not linked to an asset, so no asset brief can be built",
            details={"event_id": event_id},
        )

    asset = get_asset(conn, asset_id, timezone=timezone)
    warranty = warranty_service.compute_warranty(
        asset, timezone=timezone, expiring_soon_days=expiring_soon_days
    )

    facts: list[BriefFact] = []
    unknowns: list[str] = []
    record_ids: list[str] = [asset.asset_id]

    facts.append(BriefFact(label="Asset", value=asset.name, record_id=asset.asset_id))
    facts.append(
        BriefFact(
            label="Category / location",
            value=f"{asset.category.value} at {asset.location or 'location not recorded'}",
            record_id=asset.asset_id,
        )
    )
    brand_model = " / ".join(part for part in (asset.brand, asset.model) if part)
    if brand_model:
        facts.append(BriefFact(label="Brand and model", value=brand_model, record_id=asset.asset_id))
    else:
        facts.append(_unknown("Brand and model"))
        unknowns.append("Brand and model")

    if asset.purchase_date is not None:
        facts.append(
            BriefFact(
                label="Purchase date (as saved)",
                value=asset.purchase_date.isoformat(),
                record_id=asset.asset_id,
            )
        )
    else:
        facts.append(_unknown("Purchase date"))
        unknowns.append("Purchase date")

    if warranty.warranty_end is not None:
        facts.append(
            BriefFact(
                label="Warranty end date (as saved)",
                value=(
                    f"{warranty.warranty_end.isoformat()} - status {warranty.status.value} "
                    f"based on saved dates"
                ),
                record_id=asset.asset_id,
            )
        )
    else:
        facts.append(_unknown("Warranty end date"))
        unknowns.append("Warranty end date")

    if asset.manual_ref:
        facts.append(BriefFact(label="Manual reference", value=asset.manual_ref, record_id=asset.asset_id))
    if asset.receipt_ref:
        facts.append(BriefFact(label="Receipt reference", value=asset.receipt_ref, record_id=asset.asset_id))

    related_event_ids: list[str] = []
    if event is not None:
        record_ids.append(event.event_id)
        facts.append(
            BriefFact(
                label="Reported issue",
                value=event.description,
                record_id=event.event_id,
                source_type=event.source_type,
            )
        )
        occurred = parse_datetime(event.occurred_at, field="occurred_at")
        facts.append(
            BriefFact(
                label="Issue reported at",
                value=occurred.isoformat() if occurred else "Not recorded",
                record_id=event.event_id,
                is_unknown=occurred is None,
            )
        )
        if event.outcome:
            facts.append(
                BriefFact(label="Outcome", value=event.outcome, record_id=event.event_id)
            )

    if include_history:
        history = maintenance_service.events_for_asset(conn, asset.asset_id, limit=max_history)
        for item in history:
            if event is not None and item.event_id == event.event_id:
                continue
            related_event_ids.append(item.event_id)
            record_ids.append(item.event_id)
            facts.append(
                BriefFact(
                    label=f"Previous {item.event_type.value} ({item.occurred_at or item.created_at})",
                    value=item.description,
                    record_id=item.event_id,
                    source_type=item.source_type,
                )
            )
            if item.outcome:
                facts.append(
                    BriefFact(
                        label=f"Previous outcome ({item.event_id})",
                        value=item.outcome,
                        record_id=item.event_id,
                    )
                )

    if not unknowns:
        unknowns.append("Warranty terms and exclusions")

    summary = _deterministic_summary(asset.name, warranty.status.value, event, len(related_event_ids))
    return TechnicianBrief(
        event_id=event.event_id if event else None,
        asset_id=asset.asset_id,
        title=f"Technician brief - {asset.name}",
        summary=summary,
        facts=facts,
        unknowns=unknowns,
        related_event_ids=related_event_ids,
        record_ids=list(dict.fromkeys(record_ids)),
        summary_provider="deterministic",
        is_demo=asset.is_demo or (event.is_demo if event else False),
    )


def _deterministic_summary(
    asset_name: str, warranty_status: str, event, related_count: int
) -> str:
    """Template summary - no model involved, no invented facts."""
    if event is None:
        base = f"HomeOps brief for {asset_name}. Warranty status is {warranty_status} based on the saved dates."
    else:
        base = (
            f"HomeOps brief for {asset_name}: {event.description} "
            f"(reported {event.occurred_at or 'at an unrecorded time'}). "
            f"Warranty status is {warranty_status} based on the saved dates."
        )
    if related_count:
        base += f" {related_count} related previous record(s) are included in the facts below."
    base += " Facts are copied from stored records; unknown details are listed explicitly."
    return base


def suggest_service_category(conn: sqlite3.Connection, asset_id: str) -> ServiceCategory:
    """Map an asset category onto a service category for the handoff flow."""
    asset = get_asset(conn, asset_id)
    mapping = {
        "appliance": ServiceCategory.APPLIANCE_REPAIR,
        "hvac": ServiceCategory.APPLIANCE_REPAIR,
        "fixture": ServiceCategory.PLUMBING,
        "outdoor": ServiceCategory.GARDEN,
        "electronics": ServiceCategory.ELECTRICAL,
        "other": ServiceCategory.GENERAL,
    }
    return mapping.get(asset.category.value, ServiceCategory.GENERAL)


__all__ = [
    "build_technician_brief",
    "suggest_service_category",
    "TechnicianBrief",
]
