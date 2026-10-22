"""Handoff link generation and validation tests (checklist D and H).

The rules under test: a link is only built from data HomeOps actually holds,
every parameter is URL-encoded, and a missing or invalid contact value is
treated as missing rather than invented.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from homeops_core.errors import ValidationError
from homeops_core.models import Provider, ServiceCategory
from homeops_core.services.handoff import (
    build_handoff_payload,
    build_mailto_url,
    build_maps_search_url,
    build_message_draft,
    build_tel_url,
    build_whatsapp_url,
    is_valid_email,
    normalise_phone,
    validate_booking_url,
    validate_service_category,
)

# -- maps -------------------------------------------------------------------


def test_maps_url_encodes_service_and_locality() -> None:
    url = build_maps_search_url("appliance_repair", "Bristol")
    parsed = urlparse(url)
    assert parsed.netloc == "www.google.com"
    query = parse_qs(parsed.query)["query"][0]
    assert query == "appliance repair Bristol"


def test_maps_url_encodes_special_characters() -> None:
    url = build_maps_search_url("plumbing", "St Ives & Penzance")
    assert " " not in url
    query = parse_qs(urlparse(url).query)["query"][0]
    assert query == "plumbing St Ives & Penzance"


def test_maps_url_requires_something_to_search_for() -> None:
    with pytest.raises(ValidationError):
        build_maps_search_url("", None)


# -- whatsapp ---------------------------------------------------------------


def test_whatsapp_url_encodes_the_message_body() -> None:
    message = "Hello, I need help with my washing machine.\nIt is leaking?"
    url = build_whatsapp_url("+44 7700 900101", message)
    assert url is not None
    assert url.startswith("https://wa.me/447700900101?text=")
    assert "\n" not in url
    assert "?" not in url.split("text=")[1]


def test_whatsapp_url_is_absent_without_a_valid_number() -> None:
    assert build_whatsapp_url(None, "hi") is None
    assert build_whatsapp_url("", "hi") is None
    assert build_whatsapp_url("123", "hi") is None


def test_phone_normalisation_handles_country_prefixes() -> None:
    assert normalise_phone("+44 7700 900101") == "+447700900101"
    assert normalise_phone("0044 7700 900101") == "+447700900101"
    assert normalise_phone("07700900101") == "07700900101"
    assert normalise_phone("n/a") is None
    assert normalise_phone("+1 (555) 000-0000") == "+15550000000"


# -- tel / mailto -----------------------------------------------------------


def test_tel_url_only_when_a_number_is_stored() -> None:
    assert build_tel_url("+44 7700 900101") == "tel:+447700900101"
    assert build_tel_url(None) is None
    assert build_tel_url("call the office") is None


def test_mailto_url_encodes_subject_and_body() -> None:
    url = build_mailto_url("help@example.test", subject="Service request - plumbing", body="A leak under the sink")
    assert url is not None
    assert url.startswith("mailto:help@example.test?")
    parsed = parse_qs(urlparse(url).query)
    assert parsed["subject"][0] == "Service request - plumbing"
    assert parsed["body"][0] == "A leak under the sink"


def test_mailto_url_rejected_for_an_invalid_address() -> None:
    assert is_valid_email("not-an-email") is False
    assert is_valid_email("a@b") is False
    assert is_valid_email("a@b.test") is True
    assert build_mailto_url("not-an-email", subject="s", body="b") is None
    assert build_mailto_url(None, subject="s", body="b") is None


# -- booking page -----------------------------------------------------------


def test_booking_url_must_be_stored_https() -> None:
    assert validate_booking_url("https://book.example.test/x") == "https://book.example.test/x"
    assert validate_booking_url("http://book.example.test/x") is None
    assert validate_booking_url("javascript:alert(1)") is None
    assert validate_booking_url("https://book.example.test/a b") is None
    assert validate_booking_url(None) is None


def test_service_category_is_validated() -> None:
    assert validate_service_category("plumbing") is ServiceCategory.PLUMBING
    with pytest.raises(ValidationError):
        validate_service_category("plumbing_and_more")


# -- full payload -----------------------------------------------------------


def _provider(**overrides) -> Provider:
    base = dict(
        provider_id="provider_test",
        name="Test Provider (DEMO)",
        service_categories=[ServiceCategory.APPLIANCE_REPAIR],
        phone="+44 7700 900101",
        email="service@test.example",
        booking_url="https://book.test.example/",
        locality="Bristol",
        is_demo=True,
    )
    base.update(overrides)
    return Provider(**base)


def test_payload_includes_every_action_when_contacts_exist() -> None:
    payload = build_handoff_payload(
        provider=_provider(),
        service_category=ServiceCategory.APPLIANCE_REPAIR,
        locality="Bristol",
        message_draft="Hello",
    )
    kinds = {action.action_type for action in payload.actions}
    assert kinds == {"maps_search", "whatsapp", "tel", "mailto", "booking_page"}
    assert payload.unavailable_actions == []


def test_payload_omits_whatsapp_when_no_phone_is_stored() -> None:
    """A provider without a stored number must not get a WhatsApp or tel action."""
    payload = build_handoff_payload(
        provider=_provider(phone=None),
        service_category=ServiceCategory.APPLIANCE_REPAIR,
        locality="Bristol",
        message_draft="Hello",
    )
    kinds = {action.action_type for action in payload.actions}
    assert "whatsapp" not in kinds
    assert "tel" not in kinds
    assert "whatsapp" in payload.unavailable_actions
    assert "tel" in payload.unavailable_actions


def test_payload_without_a_provider_only_offers_a_maps_search() -> None:
    payload = build_handoff_payload(
        provider=None,
        service_category=ServiceCategory.PLUMBING,
        locality="Bristol",
        message_draft="Hello",
    )
    assert [action.action_type for action in payload.actions] == ["maps_search"]
    assert set(payload.unavailable_actions) == {"whatsapp", "tel", "mailto", "booking_page"}


def test_payload_flags_an_unvalidated_booking_url() -> None:
    payload = build_handoff_payload(
        provider=_provider(booking_url="http://insecure.example.test/"),
        service_category=ServiceCategory.APPLIANCE_REPAIR,
        locality="Bristol",
        message_draft="Hello",
    )
    assert "booking_page" not in {action.action_type for action in payload.actions}
    assert "booking_page" in payload.unavailable_actions


def test_message_draft_is_clearly_a_demo() -> None:
    draft = build_message_draft(
        asset_name="Washing Machine",
        service_category=ServiceCategory.APPLIANCE_REPAIR,
        issue_summary="Water on the floor",
        provider_name="Northfield Appliance Care (DEMO)",
    )
    assert "washing machine" in draft
    assert "Water on the floor" in draft
    assert "HomeOps" in draft
    # The draft must never look like a confirmation of a booking.
    assert "confirmed" not in draft.lower()


def test_message_draft_is_bounded() -> None:
    draft = build_message_draft(
        asset_name="Washing Machine",
        service_category=ServiceCategory.APPLIANCE_REPAIR,
        issue_summary="x" * 5000,
    )
    assert len(draft) <= 1200
