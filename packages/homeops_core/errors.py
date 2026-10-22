"""Domain errors shared by the MCP server and the FastAPI orchestrator.

Errors carry a stable ``code`` so the API can map them onto HTTP status codes
without leaking stack traces or internal details to the UI.
"""

from __future__ import annotations


class HomeOpsError(Exception):
    """Base class for every expected HomeOps failure."""

    code = "homeops_error"
    http_status = 400

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {"error": self.code, "message": self.message, "details": self.details}


class ValidationError(HomeOpsError):
    """Input failed validation (bad date, unknown enum value, oversized text)."""

    code = "invalid_input"
    http_status = 422


class NotFoundError(HomeOpsError):
    """A referenced record does not exist."""

    code = "not_found"
    http_status = 404


class StateTransitionError(HomeOpsError):
    """A record cannot move to the requested state."""

    code = "invalid_state"
    http_status = 409


class ProviderContactError(HomeOpsError):
    """Provider contact data is missing or unusable for the requested action."""

    code = "provider_contact_unavailable"
    http_status = 409


class MCPUnavailableError(HomeOpsError):
    """The MCP server could not be reached or returned an error."""

    code = "mcp_unavailable"
    http_status = 502
