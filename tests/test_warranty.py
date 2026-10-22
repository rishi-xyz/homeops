"""Warranty classification tests (checklist H).

The rule under test is narrow: HomeOps classifies the dates it holds and says
so explicitly. It must never fill in a missing date or imply a manufacturer
determination.
"""

from __future__ import annotations

from datetime import date

from homeops_core.models import Asset, SourceType, WarrantyStatus
from homeops_core.services.warranty import compute_warranty


def _asset(**overrides) -> Asset:
    base = dict(
        asset_id="asset_test_01",
        name="Test Appliance",
        category="appliance",
        location="Kitchen",
        brand="TestBrand",
        model="TB-1",
        purchase_date=date(2024, 1, 1),
        warranty_start=date(2024, 1, 1),
        warranty_end=date(2025, 1, 1),
        timezone="Europe/London",
        source_type=SourceType.DEMO_SEED,
        is_demo=True,
    )
    base.update(overrides)
    return Asset(**base)


def test_active_warranty_when_end_is_far_away() -> None:
    info = compute_warranty(
        _asset(warranty_end=date(2027, 1, 1)),
        now_date=date(2026, 10, 21),
        expiring_soon_days=30,
    )
    assert info.status is WarrantyStatus.ACTIVE
    assert info.days_remaining == 72
    assert "not a verified warranty determination" in info.basis_note


def test_expiring_soon_at_the_threshold() -> None:
    info = compute_warranty(
        _asset(warranty_end=date(2026, 11, 14)),
        now_date=date(2026, 10, 21),
        expiring_soon_days=30,
    )
    assert info.status is WarrantyStatus.EXPIRING_SOON
    assert info.days_remaining == 24


def test_expired_the_day_after_the_end_date() -> None:
    info = compute_warranty(
        _asset(warranty_end=date(2026, 10, 20)),
        now_date=date(2026, 10, 21),
        expiring_soon_days=30,
    )
    assert info.status is WarrantyStatus.EXPIRED
    assert info.days_remaining == -1


def test_unknown_when_no_end_date_is_stored() -> None:
    info = compute_warranty(
        _asset(warranty_end=None, warranty_start=None, purchase_date=None),
        now_date=date(2026, 10, 21),
    )
    assert info.status is WarrantyStatus.UNKNOWN
    assert info.days_remaining is None
    assert info.warranty_end is None
    assert "unknown" in info.basis_note.lower()


def test_unknown_status_never_invents_an_end_date() -> None:
    """A missing end date must stay missing in the derived record."""
    info = compute_warranty(_asset(warranty_end=None), now_date=date(2026, 10, 21))
    assert info.warranty_end is None
    assert info.days_remaining is None
