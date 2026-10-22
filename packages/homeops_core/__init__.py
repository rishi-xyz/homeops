"""HomeOps core: domain models, SQLite access, seed data and business rules.

Everything in this package is deliberately dependency-light so that both the
MCP server and the FastAPI orchestrator can import it without pulling in web
frameworks. Only Pydantic is required.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
