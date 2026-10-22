"""Maintenance history search tests (checklist H)."""

from __future__ import annotations

from homeops_core.services import maintenance as maintenance_service


def test_search_returns_seeded_washer_incidents(conn) -> None:
    events = maintenance_service.search_maintenance_history(conn, asset_id="asset_washer_01")
    assert len(events) >= 1
    ids = {event.event_id for event in events}
    assert "evt_washer_leak_2026_03" in ids


def test_search_by_text_finds_leak(conn) -> None:
    events = maintenance_service.search_maintenance_history(conn, query="leak")
    assert events
    assert any("leak" in event.description.lower() for event in events)


def test_search_by_event_type(conn) -> None:
    events = maintenance_service.search_maintenance_history(conn, event_type="issue")
    assert events


def test_empty_search_returns_no_results_without_inventing_anything(conn) -> None:
    """An empty result is a valid answer - the service must not fabricate records."""
    events = maintenance_service.search_maintenance_history(conn, query="completely_made_up_thing_xyz")
    assert events == []


def test_log_maintenance_event_persists_and_is_searchable(conn) -> None:
    event = maintenance_service.log_maintenance_event(
        conn,
        event_type="issue",
        description="Unusual vibration during spin cycle",
        asset_id="asset_washer_01",
        source_type="user_entered",
        is_demo=False,
    )
    assert event.event_id.startswith("evt_")
    results = maintenance_service.search_maintenance_history(conn, asset_id="asset_washer_01", query="vibration")
    assert any(item.event_id == event.event_id for item in results)
