"""Tests for the layered ``.env.<HOMEOPS_ENV>`` configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from homeops_core.config import (
    ConfigurationError,
    env_file_paths,
    get_settings,
    resolve_env_name,
)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Remove ambient HOMEOPS_* variables and point the app at ``tmp_path``."""
    for key in list(os.environ):
        if key.startswith("HOMEOPS_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOMEOPS_HOME", str(tmp_path))
    return tmp_path


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def test_env_file_paths_follow_the_selected_environment(isolated_env: Path) -> None:
    production = env_file_paths(isolated_env, "prod")

    assert production == [
        isolated_env / ".env.prod",
        isolated_env / ".env.prod.local",
    ]


def test_env_name_defaults_to_development(isolated_env: Path) -> None:
    assert resolve_env_name(None) == "dev"
    assert resolve_env_name("  Prod  ") == "prod"


def test_invalid_env_name_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        resolve_env_name("../prod")


def test_selected_environment_file_is_loaded(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_env(
        isolated_env / ".env.prod",
        {"HOMEOPS_DB_PATH": "data/production.db", "HOMEOPS_TIMEZONE": "UTC"},
    )
    monkeypatch.setenv("HOMEOPS_ENV", "prod")

    settings = get_settings()

    assert settings.db_path == isolated_env / "data" / "production.db"
    assert settings.household_timezone == "UTC"


def test_local_override_file_wins_over_base_file(isolated_env: Path) -> None:
    write_env(isolated_env / ".env.dev", {"HOMEOPS_TIMEZONE": "Europe/London"})
    write_env(isolated_env / ".env.dev.local", {"HOMEOPS_TIMEZONE": "Europe/Paris"})

    assert get_settings().household_timezone == "Europe/Paris"


def test_real_environment_variables_win_over_env_files(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_env(isolated_env / ".env.dev", {"HOMEOPS_TIMEZONE": "Europe/London"})
    monkeypatch.setenv("HOMEOPS_TIMEZONE", "Asia/Tokyo")

    assert get_settings().household_timezone == "Asia/Tokyo"


def test_legacy_root_dotenv_is_used_when_no_env_file_exists(isolated_env: Path) -> None:
    write_env(isolated_env / ".env", {"HOMEOPS_TIMEZONE": "Asia/Kolkata"})

    assert get_settings().household_timezone == "Asia/Kolkata"
