"""Shared pytest fixtures.

Every test runs against a throwaway SQLite database seeded with the fictional
demo household, so a test can never touch the developer's real local data.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from homeops_core.config import Settings, build_settings
from homeops_core.seed import seed_database

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a temporary database seeded with demo data."""
    env = dict(os.environ)
    env.update(
        {
            "HOMEOPS_HOME": str(tmp_path),
            "HOMEOPS_DB_PATH": str(tmp_path / "homeops.db"),
            "HOMEOPS_SEED_DIR": str(REPO_ROOT / "data" / "seed"),
            "HOMEOPS_TIMEZONE": "Europe/London",
            "HOMEOPS_DEMO_MODE": "true",
        }
    )
    resolved = build_settings(env)
    seed_database(resolved, reset=True)
    return resolved


@pytest.fixture()
def conn(settings: Settings) -> Iterator:
    """A transactional connection to the seeded test database."""
    from homeops_core import db

    with db.session(settings) as connection:
        yield connection
