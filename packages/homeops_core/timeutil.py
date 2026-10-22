"""Timestamp and timezone helpers.

HomeOps stores every timestamp in ISO-8601 with an explicit UTC offset, and
keeps the household timezone alongside date-based records (reminders) so a
"due at 09:00" reminder means 09:00 in the user's own timezone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from .errors import ValidationError

UTC = UTC


def utcnow() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(tz=UTC)


def utcnow_iso() -> str:
    """Current time as an ISO-8601 string with a UTC offset."""
    return utcnow().isoformat()


def parse_datetime(value: str | datetime | None, *, field: str = "timestamp") -> datetime | None:
    """Parse an ISO-8601 string into an aware datetime.

    ``None`` is returned for empty input so "unknown" stays unknown. Naive
    input is rejected - an ambiguous timestamp would silently shift when the
    household timezone changes.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError(
                f"{field} must be an ISO-8601 timestamp, got {value!r}", details={"field": field}
            ) from exc
    if parsed.tzinfo is None:
        raise ValidationError(
            f"{field} must include a timezone offset, got {value!r}", details={"field": field}
        )
    return parsed


def parse_date(value: str | date | None, *, field: str = "date") -> date | None:
    """Parse an ISO-8601 date (or the date part of a timestamp)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = value.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ValidationError(
            f"{field} must be an ISO-8601 date, got {value!r}", details={"field": field}
        ) from exc


def to_utc(moment: datetime) -> datetime:
    """Normalise an aware datetime to UTC."""
    if moment.tzinfo is None:
        raise ValidationError("Cannot convert a naive datetime to UTC")
    return moment.astimezone(UTC)


def iso(moment: datetime | None) -> str | None:
    """Serialise a datetime for storage."""
    if moment is None:
        return None
    return to_utc(moment).isoformat()


def today_in(tz_name: str) -> date:
    """Today's date in the given IANA timezone."""
    return datetime.now(tz=ZoneInfo(tz_name)).date()


def combine_local(day: date, clock: time, tz_name: str) -> datetime:
    """Combine a local date and time into an aware datetime in ``tz_name``."""
    zone = ZoneInfo(tz_name)
    return datetime.combine(day, clock, tzinfo=zone)


def format_in_zone(moment: datetime, tz_name: str) -> str:
    """Human readable timestamp in the household timezone."""
    return moment.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M %Z")


def relative_days(target: date, reference: date | None = None) -> int:
    """Whole days from ``reference`` to ``target`` (negative when in the past)."""
    reference = reference or date.today()
    return (target - reference).days
