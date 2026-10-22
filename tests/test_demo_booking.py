"""Demo booking state machine tests (checklist E and H).

The rule under test: only an explicit user confirmation can move a simulated
request to ``confirmed_demo``, and a wrong or missing reference cannot.
"""

from __future__ import annotations

import pytest
from homeops_core.errors import NotFoundError, StateTransitionError
from homeops_core.models import RequestStatus
from homeops_core.services import slots as slots_service


def _first_slot_id(conn) -> str:
    slots = slots_service.list_demo_slots(conn, service_type="appliance_repair", limit=1)
    assert slots, "the seed must provide at least one appliance slot"
    return slots[0].slot_id


def test_draft_creates_a_pending_request_and_issues_a_token(conn) -> None:
    slot_id = _first_slot_id(conn)
    request, token = slots_service.draft_service_request(conn, slot_id=slot_id, note="Demo note")
    assert request.status is RequestStatus.AWAITING_USER_ACTION
    assert token
    assert request.is_demo is True
    # Drafting must never confirm anything.
    assert request.status is not RequestStatus.CONFIRMED_DEMO


def test_confirm_requires_the_issued_token(conn) -> None:
    slot_id = _first_slot_id(conn)
    request, token = slots_service.draft_service_request(conn, slot_id=slot_id)
    with pytest.raises(StateTransitionError):
        slots_service.confirm_service_request(
            conn, request_id=request.request_id, confirmation_token="not-the-token"
        )

    # The request must still be pending after the failed attempt.
    still_pending = slots_service.get_request(conn, request.request_id)
    assert still_pending.status is RequestStatus.AWAITING_USER_ACTION


def test_confirm_with_the_issued_token_moves_to_confirmed_demo(conn) -> None:
    slot_id = _first_slot_id(conn)
    request, token = slots_service.draft_service_request(conn, slot_id=slot_id)
    confirmed = slots_service.confirm_service_request(
        conn, request_id=request.request_id, confirmation_token=token
    )
    assert confirmed.status is RequestStatus.CONFIRMED_DEMO


def test_duplicate_confirmation_is_idempotent(conn) -> None:
    slot_id = _first_slot_id(conn)
    request, token = slots_service.draft_service_request(conn, slot_id=slot_id)
    first = slots_service.confirm_service_request(
        conn, request_id=request.request_id, confirmation_token=token
    )
    second = slots_service.confirm_service_request(
        conn, request_id=request.request_id, confirmation_token=token
    )
    assert first.status is second.status is RequestStatus.CONFIRMED_DEMO
    assert first.request_id == second.request_id


def test_unknown_slot_is_rejected(conn) -> None:
    with pytest.raises(NotFoundError):
        slots_service.draft_service_request(conn, slot_id="slot_does_not_exist")
