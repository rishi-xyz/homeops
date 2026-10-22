"""Provider handoff preparation.

This module only *prepares* outbound actions. It never sends a message, never
books anything and never opens a URL. Every destination is either derived from
a stored field or a well-known public endpoint, and every parameter is URL
encoded.
"""

from __future__ import annotations

import re
import sqlite3
from urllib.parse import quote, urlencode

from ..errors import ValidationError
from ..models import HandoffAction, HandoffPayload, Provider, ServiceCategory

MAPS_SEARCH_ENDPOINT = "https://www.google.com/maps/search/"
WHATSAPP_ENDPOINT = "https://wa.me/"

_PHONE_ALLOWED = re.compile(r"[^0-9]")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_MESSAGE_LENGTH = 1200
_MAX_SERVICE_CATEGORY_LENGTH = 60


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def normalise_phone(raw: str | None) -> str | None:
    """Return an E.164-ish phone number, or ``None`` when it is unusable.

    A number is usable when it contains 7-15 digits. Anything else is treated
    as missing so HomeOps never fabricates contact details.
    """
    if not raw:
        return None
    cleaned = _PHONE_ALLOWED.sub("", raw)
    if len(cleaned) < 7 or len(cleaned) > 15:
        return None
    if raw.strip().startswith("+"):
        return f"+{cleaned}"
    if cleaned.startswith("00"):
        return f"+{cleaned[2:]}"
    return cleaned


def is_valid_email(raw: str | None) -> bool:
    return bool(raw) and bool(_EMAIL_RE.match(raw.strip()))


def validate_booking_url(raw: str | None) -> str | None:
    """Only a stored, well-formed ``https`` URL may be opened."""
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate.lower().startswith("https://"):
        return None
    if len(candidate) > 500 or " " in candidate:
        return None
    return candidate


def validate_service_category(raw: str) -> ServiceCategory:
    try:
        return ServiceCategory(raw)
    except ValueError as exc:
        raise ValidationError(
            f"Unknown service category {raw!r}",
            details={"field": "service_category", "allowed": [c.value for c in ServiceCategory]},
        ) from exc


# ---------------------------------------------------------------------------
# Link builders
# ---------------------------------------------------------------------------


def build_maps_search_url(service_category: str, locality: str | None) -> str:
    """Google Maps search link built from the user-selected service and locality."""
    service = (service_category or "").strip()[:_MAX_SERVICE_CATEGORY_LENGTH]
    place = (locality or "").strip()[:120]
    query = " ".join(part for part in (service.replace("_", " "), place) if part)
    if not query:
        raise ValidationError(
            "A service type or locality is required to build a Maps search",
            details={"field": "service_category"},
        )
    return f"{MAPS_SEARCH_ENDPOINT}?{urlencode({'api': '1', 'query': query})}"


def build_whatsapp_url(phone: str | None, message: str) -> str | None:
    """Click-to-chat link, only when a valid phone number is stored."""
    normalised = normalise_phone(phone)
    if normalised is None:
        return None
    body = (message or "").strip()[:_MAX_MESSAGE_LENGTH]
    digits = normalised.lstrip("+")
    return f"{WHATSAPP_ENDPOINT}{digits}?text={quote(body, safe='')}"


def build_tel_url(phone: str | None) -> str | None:
    """``tel:`` link, only when a valid phone number is stored."""
    normalised = normalise_phone(phone)
    if normalised is None:
        return None
    return f"tel:{normalised}"


def build_mailto_url(email: str | None, *, subject: str, body: str) -> str | None:
    """``mailto:`` link, only when a valid email address is stored."""
    if not is_valid_email(email):
        return None
    clean_email = email.strip()
    query = urlencode({"subject": subject[:200], "body": body[:_MAX_MESSAGE_LENGTH]})
    return f"mailto:{clean_email}?{query}"


# ---------------------------------------------------------------------------
# Handoff payload
# ---------------------------------------------------------------------------


def build_message_draft(
    *,
    asset_name: str | None,
    service_category: ServiceCategory,
    issue_summary: str | None,
    brief_lines: list[str] | None = None,
    provider_name: str | None = None,
) -> str:
    """Build the outbound message text shown to the user before it is opened."""
    lines: list[str] = []
    greeting = f"Hello{' ' + provider_name if provider_name else ''},"
    lines.append(greeting)
    lines.append("")
    if asset_name:
        lines.append(f"I need help with my {asset_name.lower()}.")
    lines.append(f"Service needed: {service_category.value.replace('_', ' ')}.")
    if issue_summary:
        lines.append(f"Issue: {issue_summary}")
    for line in brief_lines or []:
        lines.append(f"- {line}")
    lines.append("")
    lines.append("Could you let me know your availability and an estimated cost?")
    lines.append("")
    lines.append("Sent from HomeOps (household maintenance demo).")
    return "\n".join(lines)[:_MAX_MESSAGE_LENGTH]


def build_handoff_payload(
    *,
    provider: Provider | None,
    service_category: ServiceCategory,
    locality: str | None,
    message_draft: str | None,
    technician_brief=None,
    issue_event_id: str | None = None,
    asset_id: str | None = None,
) -> HandoffPayload:
    """Assemble the reviewable handoff card for the UI."""
    actions: list[HandoffAction] = []
    unavailable: list[str] = []

    # 1. Maps search - always possible when there is a service category.
    maps_url = build_maps_search_url(service_category.value, locality)
    actions.append(
        HandoffAction(
            action_type="maps_search",
            label="Search Google Maps",
            url=maps_url,
            recipient=None,
            note="Opens a Maps search for this service type and locality. It does not contact anyone.",
        )
    )

    phone = provider.phone if provider else None
    email = provider.email if provider else None
    booking_url = validate_booking_url(provider.booking_url) if provider else None

    if provider is None:
        unavailable.append("whatsapp")
        unavailable.append("tel")
        unavailable.append("mailto")
        unavailable.append("booking_page")
    else:
        whatsapp_url = build_whatsapp_url(phone, message_draft or "")
        if whatsapp_url:
            actions.append(
                HandoffAction(
                    action_type="whatsapp",
                    label="Open WhatsApp with a prefilled draft",
                    url=whatsapp_url,
                    recipient=phone,
                    message_preview=message_draft,
                    note="Opens WhatsApp with a prefilled message. You still have to press send.",
                )
            )
        else:
            unavailable.append("whatsapp")

        tel_url = build_tel_url(phone)
        if tel_url:
            actions.append(
                HandoffAction(
                    action_type="tel",
                    label=f"Call {provider.name}",
                    url=tel_url,
                    recipient=phone,
                )
            )
        else:
            unavailable.append("tel")

        mailto_url = build_mailto_url(
            email,
            subject=f"Service request - {service_category.value.replace('_', ' ')}",
            body=message_draft or "",
        )
        if mailto_url:
            actions.append(
                HandoffAction(
                    action_type="mailto",
                    label=f"Email {provider.name}",
                    url=mailto_url,
                    recipient=email,
                    message_preview=message_draft,
                    note="Opens your mail client with a prefilled draft. You still have to press send.",
                )
            )
        else:
            unavailable.append("mailto")

        if booking_url:
            actions.append(
                HandoffAction(
                    action_type="booking_page",
                    label=f"Open {provider.name} booking page",
                    url=booking_url,
                    recipient=provider.name,
                    note="Opens the provider's own website. HomeOps does not submit anything for you.",
                )
            )
        else:
            unavailable.append("booking_page")

    return HandoffPayload(
        issue_event_id=issue_event_id,
        asset_id=asset_id,
        service_category=service_category,
        locality=locality,
        provider=provider,
        technician_brief=technician_brief,
        actions=actions,
        unavailable_actions=unavailable,
        message_draft=message_draft,
    )


def record_handoff_opened(
    conn: sqlite3.Connection, request_id: str, *, channel: str
) -> None:
    """Record that a user opened an external link.

    The strongest claim HomeOps may make is ``handoff_opened``. A click never
    means the message was sent or the appointment was accepted.
    """
    conn.execute(
        """
        UPDATE service_requests
        SET status = CASE WHEN status IN ('draft', 'awaiting_user_action') THEN 'handoff_opened' ELSE status END,
            channel = ?
        WHERE request_id = ?
        """,
        (channel, request_id),
    )
