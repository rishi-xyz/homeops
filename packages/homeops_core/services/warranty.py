"""Warranty classification.

The rule is deliberately narrow: HomeOps classifies the *saved dates* it holds.
It never asserts that a manufacturer would honour a claim, and it never fills
in a missing date.
"""

from __future__ import annotations

from datetime import date

from ..models import Asset, SourceType, WarrantyInfo, WarrantyStatus
from ..timeutil import today_in

UNKNOWN_BASIS = (
    "No warranty end date is stored for this item, so warranty status is unknown. "
    "This is not a verified warranty determination."
)


def compute_warranty(
    asset: Asset,
    *,
    now_date: date | None = None,
    timezone: str | None = None,
    expiring_soon_days: int = 30,
) -> WarrantyInfo:
    """Classify a warranty from the dates stored on ``asset``."""
    tz_name = timezone or asset.timezone
    today = now_date or today_in(tz_name)
    threshold = max(0, expiring_soon_days)

    if asset.warranty_end is None:
        return WarrantyInfo(
            status=WarrantyStatus.UNKNOWN,
            purchase_date=asset.purchase_date,
            warranty_start=asset.warranty_start,
            warranty_end=None,
            days_remaining=None,
            expiring_soon_days=threshold,
            source_type=asset.source_type,
            basis_note=UNKNOWN_BASIS,
        )

    days_remaining = (asset.warranty_end - today).days
    if days_remaining < 0:
        status = WarrantyStatus.EXPIRED
    elif days_remaining <= threshold:
        status = WarrantyStatus.EXPIRING_SOON
    else:
        status = WarrantyStatus.ACTIVE

    return WarrantyInfo(
        status=status,
        purchase_date=asset.purchase_date,
        warranty_start=asset.warranty_start,
        warranty_end=asset.warranty_end,
        days_remaining=days_remaining,
        expiring_soon_days=threshold,
        source_type=asset.source_type,
        verified_by_official_source=False,
        basis_note=(
            f"Based on the dates saved in HomeOps (warranty recorded as ending {asset.warranty_end.isoformat()}). "
            "This is not a verified warranty determination - check the manufacturer policy and proof of purchase."
        ),
    )


def warranty_source_label(source_type: SourceType) -> str:
    """Short human readable provenance label."""
    match source_type:
        case SourceType.DEMO_SEED:
            return "Demo seed record (fictional)"
        case SourceType.PROVIDER_REPORTED:
            return "Reported by a provider"
        case _:
            return "Entered by the user"
