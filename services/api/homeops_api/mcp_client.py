"""MCP client session manager.

The orchestrator talks to the HomeOps MCP server through a real MCP client
over Streamable HTTP. One session is kept open for the lifetime of the API
process and re-established transparently if the server restarts.

Every call is recorded as a :class:`ToolCallRecord` so the UI can show exactly
which tools ran, whether they succeeded and which records they touched.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass, field
from typing import Any

from homeops_core.errors import (
    HomeOpsError,
    MCPUnavailableError,
    NotFoundError,
    StateTransitionError,
    ValidationError,
)
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Domain error codes map back onto the HTTP status the API should return. The
# MCP server embeds the code in the tool error message (``[not_found] ...``).
_ERROR_CODE_MAP: dict[str, type[HomeOpsError]] = {
    "invalid_input": ValidationError,
    "not_found": NotFoundError,
    "invalid_state": StateTransitionError,
    "provider_contact_unavailable": StateTransitionError,
    "mcp_unavailable": MCPUnavailableError,
}


def map_tool_error(message: str, record: ToolCallRecord | None = None) -> HomeOpsError:
    """Map an MCP tool error message back onto a domain error.

    The MCP tool surface returns errors as structured results rather than
    transport failures, so the API has to translate them itself to keep the
    HTTP status codes meaningful.
    """
    text = str(message or "The tool returned an error.")
    code = None
    marker = text.find("[")
    if marker != -1 and "]" in text[marker:]:
        candidate = text[marker + 1 : text.index("]", marker)]
        if candidate in _ERROR_CODE_MAP:
            code = candidate
    error_cls = _ERROR_CODE_MAP.get(code or "")
    if error_cls is None:
        return MCPUnavailableError(text)
    clean = text[text.index("]") + 1 :].strip() if code else text
    if not clean:
        clean = text
    return error_cls(clean, details={"tool_error": text, "record_ids": record.record_ids if record else []})



@dataclass
class ToolCallRecord:
    """One MCP tool invocation, as shown in the UI activity panel."""

    name: str
    status: str
    duration_ms: int
    record_ids: list[str] = field(default_factory=list)
    summary: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "record_ids": self.record_ids,
            "summary": self.summary,
            "error": self.error,
        }


class MCPClientManager:
    """Keeps a live MCP client session against the HomeOps MCP server."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._lock = asyncio.Lock()
        self.protocol_version: str | None = None
        self.server_info: dict[str, Any] = {}
        self.last_error: str | None = None

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Open the session and initialise it. Safe to call twice."""
        async with self._lock:
            await self._open()

    async def stop(self) -> None:
        """Close the session."""
        async with self._lock:
            if self._stack is not None:
                try:
                    await self._stack.aclose()
                finally:
                    self._stack = None
                    self._session = None
                    self.protocol_version = None

    async def _open(self) -> None:
        stack = AsyncExitStack()
        try:
            read, write, *_rest = await stack.enter_async_context(streamable_http_client(self.url))
            session = await stack.enter_async_context(ClientSession(read, write))
            init = await session.initialize()
        except Exception as exc:
            await stack.aclose()
            self.last_error = str(exc)
            raise MCPUnavailableError(
                f"Could not connect to the HomeOps MCP server at {self.url}: {exc}"
            ) from exc

        self._stack = stack
        self._session = session
        self.protocol_version = init.protocol_version
        self.server_info = {
            "name": getattr(init.server_info, "name", None),
            "version": getattr(init.server_info, "version", None),
            "title": getattr(init.server_info, "title", None),
        }
        self.last_error = None

    async def _ensure_session(self) -> ClientSession:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is None:
                await self._open()
        assert self._session is not None
        return self._session

    async def _reset(self) -> None:
        if self._stack is not None:
            with suppress(Exception):
                await self._stack.aclose()
        self._stack = None
        self._session = None

    # -- operations --------------------------------------------------------

    async def list_tools(self) -> list[dict[str, Any]]:
        """List the tools the MCP server exposes."""
        session = await self._ensure_session()
        try:
            result = await session.list_tools()
        except Exception as exc:
            await self._reset()
            raise MCPUnavailableError(f"tools/list failed: {exc}") from exc
        return [
            {
                "name": tool.name,
                "title": getattr(tool, "title", None),
                "description": getattr(tool, "description", None),
                "input_schema": getattr(tool, "input_schema", None),
            }
            for tool in result.tools
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        record_ids: list[str] | None = None,
    ) -> tuple[dict[str, Any], ToolCallRecord]:
        """Call a tool and return its structured payload plus the trace record."""
        started = time.perf_counter()
        session = await self._ensure_session()
        try:
            result = await session.call_tool(name, arguments or {})
        except Exception as exc:
            await self._reset()
            record = ToolCallRecord(
                name=name,
                status="error",
                duration_ms=int((time.perf_counter() - started) * 1000),
                record_ids=record_ids or [],
                error=str(exc),
            )
            raise MCPUnavailableError(f"tools/call {name} failed: {exc}") from exc

        duration = int((time.perf_counter() - started) * 1000)
        is_error = bool(getattr(result, "is_error", False))

        payload: dict[str, Any] = {}
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict):
            payload = structured
        else:
            text = " ".join(
                block.text for block in (result.content or []) if getattr(block, "text", None)
            )
            payload = {"text": text}

        if is_error:
            message = payload.get("text") or "The tool returned an error."
            record = ToolCallRecord(
                name=name,
                status="error",
                duration_ms=duration,
                record_ids=record_ids or [],
                error=str(message),
            )
            # A tool-level error is a domain outcome (not found, invalid input,
            # illegal state transition), so surface it as a mapped HomeOps error
            # instead of a silent 200 with an error payload.
            raise map_tool_error(message, record)

        record = ToolCallRecord(
            name=name,
            status="success",
            duration_ms=duration,
            record_ids=record_ids or _extract_record_ids(payload),
            summary=_extract_summary(payload),
        )
        return payload, record

    @property
    def connected(self) -> bool:
        return self._session is not None


def _extract_record_ids(payload: dict[str, Any]) -> list[str]:
    """Pull record IDs out of a tool payload without guessing."""
    found: list[str] = []
    for key in ("asset_id", "event_id", "reminder_id", "request_id", "provider_id", "slot_id"):
        value = payload.get(key)
        if isinstance(value, str):
            found.append(value)
    for key in ("assets", "events", "reminders", "slots", "requests", "providers", "record_ids"):
        items = payload.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    found.append(item)
                elif isinstance(item, dict):
                    for id_key in ("asset_id", "event_id", "reminder_id", "request_id", "provider_id", "slot_id"):
                        value = item.get(id_key)
                        if isinstance(value, str):
                            found.append(value)
    return list(dict.fromkeys(found))


def _extract_summary(payload: dict[str, Any]) -> str | None:
    for key in ("message", "summary", "notice"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value[:200]
    count = payload.get("count")
    if isinstance(count, int):
        return f"{count} record(s)"
    return None
