"""Asset creation tests (purchase tracking)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from homeops_core.errors import ValidationError
from homeops_core.models import AssetCategory, SourceType, WarrantyStatus
from homeops_core.services import assets as assets_service


def test_create_asset_stores_supplied_fields_and_leaves_dates_unknown(conn) -> None:
    asset = assets_service.create_asset(
        conn,
        name="  Fridge Freezer  ",
        brand="AuraCool",
        location="Kitchen",
    )

    assert asset.asset_id.startswith("asset_")
    assert asset.name == "Fridge Freezer"
    assert asset.category is AssetCategory.APPLIANCE
    assert asset.brand == "AuraCool"
    assert asset.location == "Kitchen"
    assert asset.purchase_date is None
    assert asset.warranty_start is None
    assert asset.warranty_end is None
    assert asset.source_type is SourceType.USER_ENTERED
    assert asset.is_demo is False
    assert asset.created_at is not None


def test_create_asset_with_dates_is_readable_through_list_and_detail(conn) -> None:
    purchase = date.today() - timedelta(days=10)
    warranty_end = date.today() + timedelta(days=355)

    asset = assets_service.create_asset(
        conn,
        name="Dishwasher",
        category=AssetCategory.APPLIANCE,
        purchase_date=purchase.isoformat(),
        warranty_start=purchase.isoformat(),
        warranty_end=warranty_end.isoformat(),
    )

    listed = {item.asset_id: item for item in assets_service.list_assets(conn)}
    assert asset.asset_id in listed
    assert listed[asset.asset_id].warranty_status is WarrantyStatus.ACTIVE

    detail = assets_service.get_asset_detail(conn, asset.asset_id)
    assert detail.asset.purchase_date == purchase
    assert detail.warranty.warranty_end == warranty_end
    assert detail.recent_event_ids == []
    assert detail.open_reminder_ids == []


def test_create_asset_rejects_empty_name(conn) -> None:
    with pytest.raises(ValidationError):
        assets_service.create_asset(conn, name="   ")


def test_create_asset_rejects_a_malformed_date(conn) -> None:
    with pytest.raises(ValidationError):
        assets_service.create_asset(conn, name="Microwave", warranty_end="not-a-date")


def test_create_asset_rejects_reversed_warranty_dates(conn) -> None:
    with pytest.raises(ValidationError):
        assets_service.create_asset(
            conn,
            name="Oven",
            warranty_start="2026-06-01",
            warranty_end="2026-05-01",
        )


def test_create_asset_rejects_an_unknown_timezone(conn) -> None:
    with pytest.raises(ValidationError):
        assets_service.create_asset(conn, name="Kettle", timezone="Mars/Olympus_Mons")


def test_create_asset_rejects_an_unknown_category(conn) -> None:
    with pytest.raises(ValidationError):
        assets_service.create_asset(conn, name="Mystery box", category="spaceship")
