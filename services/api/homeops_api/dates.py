"""Small deterministic date parser for the assistant router.

The router never guesses. It recognises a small, explicit set of date phrases
and returns ``None`` when the message does not contain one - in that case the
assistant asks a follow-up question instead of inventing a due date.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I)
_IN_N = re.compile(r"\bin\s+(\d{1,3})\s+(day|days|week|weeks|month|months)\b", re.I)
_TIME = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_TIME_24 = re.compile(r"\b(?:at\s+)(\d{1,2}):(\d{2})\b")
_NEXT_WEEKDAY = re.compile(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_due_datetime(message: str, tz_name: str) -> datetime | None:
    """Extract a due date and time from a message, or return ``None``."""
    zone = ZoneInfo(tz_name)
    text = (message or "").strip()
    if not text:
        return None

    day: date | None = None
    clock: time = time(9, 0)

    iso = _ISO_DATE.search(text)
    if iso:
        try:
            day = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            day = None

    if day is None:
        month_match = _DAY_MONTH.search(text)
        if month_match:
            day_of_month = int(month_match.group(1))
            month = _MONTHS[month_match.group(2).lower()]
            today = datetime.now(tz=zone).date()
            year = today.year
            candidate = date(year, month, day_of_month)
            if candidate < today:
                candidate = date(year + 1, month, day_of_month)
            day = candidate

    if day is None:
        lowered = text.lower()
        if "day after tomorrow" in lowered:
            day = datetime.now(tz=zone).date() + timedelta(days=2)
        elif "tomorrow" in lowered:
            day = datetime.now(tz=zone).date() + timedelta(days=1)
        elif re.search(r"\btoday\b", lowered):
            day = datetime.now(tz=zone).date()

    if day is None:
        relative = _IN_N.search(text)
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2).lower()
            today = datetime.now(tz=zone).date()
            if unit.startswith("day"):
                day = today + timedelta(days=amount)
            elif unit.startswith("week"):
                day = today + timedelta(weeks=amount)
            else:
                month = today.month + amount
                year = today.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                day = date(year, month, min(today.day, 28))

    if day is None:
        weekday = _NEXT_WEEKDAY.search(text)
        if weekday:
            target = WEEKDAYS[weekday.group(1).lower()]
            today = datetime.now(tz=zone).date()
            delta = (target - today.weekday()) % 7 or 7
            day = today + timedelta(days=delta)

    if day is None:
        return None

    clock_24 = _TIME_24.search(text)
    if clock_24:
        hour, minute = int(clock_24.group(1)), int(clock_24.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            clock = time(hour, minute)
    else:
        clock_match = _TIME.search(text)
        if clock_match:
            hour = int(clock_match.group(1))
            minute = int(clock_match.group(2) or 0)
            meridiem = (clock_match.group(3) or "").lower()
            if meridiem == "pm" and hour < 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                clock = time(hour, minute)

    return datetime.combine(day, clock, tzinfo=zone)
