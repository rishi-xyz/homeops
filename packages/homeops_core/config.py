"""Environment-driven configuration for every HomeOps process.

Settings are read from the process environment, optionally seeded from
``.env.<HOMEOPS_ENV>`` (default: ``.env.dev``). No secret is ever stored in this
module: AWS credentials are resolved through the standard AWS credential chain
by ``boto3`` itself.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ENV_NAME = "dev"
ENV_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


class ConfigurationError(RuntimeError):
    """Raised when the environment contains an unusable configuration value."""


def _env_bool(name: str, default: bool, env: dict[str, str]) -> bool:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ConfigurationError(f"{name} must be a boolean value, got {raw!r}")


def _env_int(name: str, default: int, env: dict[str, str]) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc


def _env_str(name: str, default: str | None, env: dict[str, str]) -> str | None:
    raw = env.get(name)
    if raw is None:
        return default
    raw = raw.strip()
    return raw or None


def load_dotenv(path: Path) -> dict[str, str]:
    """Read a ``.env`` file without overriding real environment variables.

    Returns the parsed mapping so callers can merge it into ``os.environ``.
    """
    parsed: dict[str, str] = {}
    if not path.is_file():
        return parsed
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        parsed[key.strip()] = value
    return parsed


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration."""

    home: Path
    db_path: Path
    seed_dir: Path
    household_timezone: str
    expiring_soon_days: int
    demo_mode: bool
    mcp_host: str
    mcp_port: int
    mcp_path: str
    mcp_url: str
    api_host: str
    api_port: int
    web_port: int
    summary_provider: str
    aws_region: str | None = None
    bedrock_model_id: str | None = None
    extra: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def tzinfo(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.household_timezone)
        except ZoneInfoNotFoundError as exc:  # pragma: no cover - defensive
            raise ConfigurationError(
                f"HOMEOPS_TIMEZONE {self.household_timezone!r} is not a known IANA timezone"
            ) from exc

    @property
    def bedrock_configured(self) -> bool:
        """True when Bedrock is selected *and* the minimum config is present."""
        return bool(self.summary_provider == "bedrock" and self.bedrock_model_id)

    def ensure_directories(self) -> None:
        """Create the local directories HomeOps writes into."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def public_summary(self) -> dict[str, object]:
        """Configuration view safe to expose over HTTP - no secrets."""
        return {
            "demo_mode": self.demo_mode,
            "household_timezone": self.household_timezone,
            "expiring_soon_days": self.expiring_soon_days,
            "mcp_url": self.mcp_url,
            "summary_provider": self.summary_provider,
            "bedrock_configured": self.bedrock_configured,
            "database": str(self.db_path),
            "seed_dir": str(self.seed_dir),
        }


def build_settings(env: dict[str, str] | None = None) -> Settings:
    """Build a :class:`Settings` object from an environment mapping."""
    env = dict(os.environ if env is None else env)

    home = Path(_env_str("HOMEOPS_HOME", str(REPO_ROOT), env) or REPO_ROOT).expanduser().resolve()

    db_raw = _env_str("HOMEOPS_DB_PATH", "data/local/homeops.db", env) or "data/local/homeops.db"
    db_path = Path(db_raw).expanduser()
    if not db_path.is_absolute():
        db_path = (home / db_path).resolve()

    seed_raw = _env_str("HOMEOPS_SEED_DIR", "data/seed", env) or "data/seed"
    seed_dir = Path(seed_raw).expanduser()
    if not seed_dir.is_absolute():
        seed_dir = (home / seed_dir).resolve()

    timezone = _env_str("HOMEOPS_TIMEZONE", "Europe/London", env) or "Europe/London"
    # Fail fast on a bad timezone rather than at the first reminder query.
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError(f"HOMEOPS_TIMEZONE {timezone!r} is not a known IANA timezone") from exc

    mcp_host = _env_str("HOMEOPS_MCP_HOST", "127.0.0.1", env) or "127.0.0.1"
    mcp_port = _env_int("HOMEOPS_MCP_PORT", 8001, env)
    mcp_path = _env_str("HOMEOPS_MCP_PATH", "/mcp", env) or "/mcp"
    mcp_url = _env_str("HOMEOPS_MCP_URL", f"http://{mcp_host}:{mcp_port}{mcp_path}", env)

    api_host = _env_str("HOMEOPS_API_HOST", "127.0.0.1", env) or "127.0.0.1"
    api_port = _env_int("HOMEOPS_API_PORT", 8000, env)
    web_port = _env_int("HOMEOPS_WEB_PORT", 3000, env)

    provider = (_env_str("HOMEOPS_SUMMARY_PROVIDER", "deterministic", env) or "deterministic").lower()
    if provider not in {"deterministic", "bedrock"}:
        raise ConfigurationError(
            f"HOMEOPS_SUMMARY_PROVIDER must be 'deterministic' or 'bedrock', got {provider!r}"
        )

    return Settings(
        home=home,
        db_path=db_path,
        seed_dir=seed_dir,
        household_timezone=timezone,
        expiring_soon_days=_env_int("HOMEOPS_EXPIRING_SOON_DAYS", 30, env),
        demo_mode=_env_bool("HOMEOPS_DEMO_MODE", True, env),
        mcp_host=mcp_host,
        mcp_port=mcp_port,
        mcp_path=mcp_path,
        mcp_url=mcp_url or f"http://{mcp_host}:{mcp_port}{mcp_path}",
        api_host=api_host,
        api_port=api_port,
        web_port=web_port,
        summary_provider=provider,
        aws_region=_env_str("AWS_REGION", None, env),
        bedrock_model_id=_env_str("BEDROCK_MODEL_ID", None, env),
    )


def resolve_env_name(raw: str | None = None) -> str:
    """Validate and normalise the selected environment name."""
    name = (raw or DEFAULT_ENV_NAME).strip().lower()
    if not ENV_NAME_PATTERN.fullmatch(name):
        raise ConfigurationError(
            f"HOMEOPS_ENV must be a simple name such as 'dev' or 'prod', got {name!r}"
        )
    return name


def env_file_paths(home: Path, env_name: str | None = None) -> list[Path]:
    """Dotenv files for the selected environment, in load order.

    ``.env.<name>`` provides the environment defaults and
    ``.env.<name>.local`` can hold personal overrides.
    """
    name = resolve_env_name(env_name or os.environ.get("HOMEOPS_ENV"))
    return [home / f".env.{name}", home / f".env.{name}.local"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, cached after the first call."""
    env = dict(os.environ)
    home = Path(env.get("HOMEOPS_HOME", str(REPO_ROOT))).expanduser()
    dotenv_paths = env_file_paths(home)
    values: dict[str, str] = {}
    for dotenv_path in dotenv_paths:
        values.update(load_dotenv(dotenv_path))
    if not dotenv_paths[0].exists():
        # Backwards compatibility: a single repository-root .env file.
        values.update(load_dotenv(home / ".env"))
    env.update({k: v for k, v in values.items() if k not in env})
    return build_settings(env)
