"""Technician brief tests: facts must match the database (checklist H)."""

from __future__ import annotations

from homeops_core.services import assets as assets_service
from homeops_core.services import brief as brief_service


def test_brief_facts_come_from_stored_records(conn) -> None:
    brief = brief_service.build_technician_brief(
        conn,
        asset_id="asset_washer_01",
        include_history=True,
        expiring_soon_days=30,
        timezone="Europe/London",
    )
    assert brief.asset_id == "asset_washer_01"
    assert "asset_washer_01" in brief.record_ids

    facts = {fact.label: fact.value for fact in brief.facts if not fact.is_unknown}
    assert facts["Asset"] == "Washing Machine"
    assert "AquaLine" in facts["Brand and model"]

    # The warranty end fact must match the stored asset record exactly.
    detail = assets_service.get_asset_detail(
        conn, "asset_washer_01", expiring_soon_days=30, timezone="Europe/London"
    )
    stored_end = detail.asset.warranty_end
    assert stored_end is not None
    assert stored_end.isoformat() in facts["Warranty end date (as saved)"]


def test_brief_lists_unknowns_instead_of_inventing_them(conn) -> None:
    """The dishwasher seed has no purchase or warranty dates at all."""
    brief = brief_service.build_technician_brief(
        conn,
        asset_id="asset_dishwasher_01",
        include_history=False,
        expiring_soon_days=30,
        timezone="Europe/London",
    )
    unknown_labels = {fact.label for fact in brief.facts if fact.is_unknown}
    assert any("Warranty" in label for label in unknown_labels)
    assert any("Purchase" in label for label in unknown_labels)
    # Unknown facts must be an explicit "not recorded" value, never a
    # fabricated date or identifier.
    for fact in brief.facts:
        if fact.is_unknown:
            assert fact.record_id is None
            assert fact.value is None or "not recorded" in str(fact.value).lower()


def test_brief_history_facts_reference_source_event_ids(conn) -> None:
    brief = brief_service.build_technician_brief(
        conn,
        asset_id="asset_washer_01",
        include_history=True,
        expiring_soon_days=30,
        timezone="Europe/London",
    )
    assert "evt_washer_leak_2026_03" in brief.record_ids
