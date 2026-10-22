"""Provider records.

Provider contact data is either explicitly supplied by the user or part of the
fictional demo seed. Nothing here is ever invented: a missing phone number
means "no phone action", not a placeholder.
"""

from __future__ import annotations

import json
import sqlite3

from ..errors import NotFoundError
from ..models import Provider, ServiceCategory, SourceType

MAX_LIST_LIMIT = 50


def _provider_from_row(row: sqlite3.Row) -> Provider:
    try:
        categories = json.loads(row["service_categories"])
    except (TypeError, json.JSONDecodeError):  # pragma: no cover - defensive
        categories = []
    valid: list[ServiceCategory] = []
    for item in categories or []:
        try:
            valid.append(ServiceCategory(item))
        except ValueError:
            continue
    return Provider(
        provider_id=row["provider_id"],
        name=row["name"],
        service_categories=valid,
        phone=row["phone"],
        email=row["email"],
        booking_url=row["booking_url"],
        locality=row["locality"],
        source_type=SourceType(row["source_type"]),
        source_ref=row["source_ref"],
        is_demo=bool(row["is_demo"]),
    )


def list_providers(
    conn: sqlite3.Connection,
    *,
    service_category: ServiceCategory | None = None,
    limit: int = MAX_LIST_LIMIT,
) -> list[Provider]:
    """List providers, optionally filtered by service category."""
    limit = max(1, min(int(limit or MAX_LIST_LIMIT), MAX_LIST_LIMIT))
    providers = [_provider_from_row(row) for row in conn.execute("SELECT * FROM providers ORDER BY name").fetchall()]
    if service_category is not None:
        providers = [p for p in providers if service_category in p.service_categories]
    return providers[:limit]


def get_provider(conn: sqlite3.Connection, provider_id: str) -> Provider:
    """Return one provider record."""
    row = conn.execute("SELECT * FROM providers WHERE provider_id = ?", (provider_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No provider found with id {provider_id!r}", details={"provider_id": provider_id})
    return _provider_from_row(row)


def find_provider_for_service(
    conn: sqlite3.Connection, service_category: ServiceCategory, *, provider_id: str | None = None
) -> Provider | None:
    """Pick the provider used for a handoff: explicit id first, then category match."""
    if provider_id:
        return get_provider(conn, provider_id)
    matches = list_providers(conn, service_category=service_category)
    return matches[0] if matches else None
