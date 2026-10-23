"""Deterministic intent router and orchestrator.

The assistant is intentionally allowlisted: a message is matched against a
small set of known intents, and each intent maps to one or more MCP tools.
When the message is ambiguous, the assistant asks a follow-up question instead
of inventing a detail.

Every primary action goes through the MCP client, so the tool trace returned
to the UI is always a record of real tool calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from homeops_core.config import Settings
from homeops_core.errors import HomeOpsError
from homeops_core.models import AssetCategory
from homeops_core.timeutil import today_in

from .dates import parse_due_datetime
from .mcp_client import MCPClientManager, ToolCallRecord
from .summary import PROVIDER_DETERMINISTIC, SummaryProvider

# ---------------------------------------------------------------------------
# Asset kinds the "I bought ..." intent understands. Longest names first so
# "fridge freezer" wins over "fridge" and "washing machine" over "washer".
# ---------------------------------------------------------------------------

ASSET_NOUNS: tuple[tuple[str, str, AssetCategory], ...] = (
    ("washing machine", "Washing Machine", AssetCategory.APPLIANCE),
    ("washer dryer", "Washer Dryer", AssetCategory.APPLIANCE),
    ("washer", "Washing Machine", AssetCategory.APPLIANCE),
    ("tumble dryer", "Tumble Dryer", AssetCategory.APPLIANCE),
    ("dryer", "Tumble Dryer", AssetCategory.APPLIANCE),
    ("dishwasher", "Dishwasher", AssetCategory.APPLIANCE),
    ("fridge freezer", "Fridge Freezer", AssetCategory.APPLIANCE),
    ("refrigerator", "Fridge Freezer", AssetCategory.APPLIANCE),
    ("fridge", "Fridge", AssetCategory.APPLIANCE),
    ("freezer", "Freezer", AssetCategory.APPLIANCE),
    ("oven", "Oven", AssetCategory.APPLIANCE),
    ("cooker", "Cooker", AssetCategory.APPLIANCE),
    ("hob", "Hob", AssetCategory.APPLIANCE),
    ("microwave", "Microwave", AssetCategory.APPLIANCE),
    ("boiler", "Boiler", AssetCategory.HVAC),
    ("heat pump", "Heat Pump", AssetCategory.HVAC),
    ("air conditioner", "Air Conditioner", AssetCategory.HVAC),
    ("air con", "Air Conditioner", AssetCategory.HVAC),
    ("radiator", "Radiator", AssetCategory.HVAC),
    ("television", "Television", AssetCategory.ELECTRONICS),
    ("tv", "Television", AssetCategory.ELECTRONICS),
    ("vacuum cleaner", "Vacuum Cleaner", AssetCategory.APPLIANCE),
    ("vacuum", "Vacuum Cleaner", AssetCategory.APPLIANCE),
    ("lawn mower", "Lawn Mower", AssetCategory.OUTDOOR),
    ("mower", "Lawn Mower", AssetCategory.OUTDOOR),
    ("coffee machine", "Coffee Machine", AssetCategory.APPLIANCE),
    ("kettle", "Kettle", AssetCategory.APPLIANCE),
    ("toaster", "Toaster", AssetCategory.APPLIANCE),
    ("laptop", "Laptop", AssetCategory.ELECTRONICS),
)

ASSET_NOUN_REGEX = "|".join(re.escape(noun) for noun, _, _ in ASSET_NOUNS)

# ---------------------------------------------------------------------------
# Intent patterns (ordered - the first match wins)
# ---------------------------------------------------------------------------

INTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("create_reminder", re.compile(r"\bremind(?:er)?\b", re.I)),
    ("technician_brief", re.compile(r"\bbrief\b|\bhand[ -]?over\b|\bsummary for\b", re.I)),
    (
        "service_handoff",
        re.compile(
            r"\bcontact\b|\bfind (?:a|an|some) (?:technician|repairer|engineer|service)\b"
            r"|\bcall\b|\bwhatsapp\b|\bemail\b|\bquote\b|\bget a quote\b|\bservice provider\b",
            re.I,
        ),
    ),
    ("demo_slots", re.compile(r"\bslot\b|\bavailability\b|\bavailable times?\b|\bappointment\b", re.I)),
    (
        "maintenance_history",
        re.compile(
            r"\bhappened before\b|\bseen (?:this|it) before\b|\bprevious\b|\blast time\b"
            r"|\bhistory\b|\bprior\b|\bagain\b|\bbefore\b",
            re.I,
        ),
    ),
    (
        "log_event",
        re.compile(
            r"\bleak(?:ing|s)?\b|\bbroken\b|\bnot working\b|\bnoise\b|\bfault(?:y)?\b"
            r"|\bissue with\b|\bproblem\b|\breport(?:ing)?\b|\bstruck\b",
            re.I,
        ),
    ),
    (
        "add_asset",
        re.compile(
            rf"\b(?:bought|purchased)\b[^.?!]*\b(?:{ASSET_NOUN_REGEX})s?\b"
            rf"|\b(?:got|received|installed)\s+(?:a|an|the|my|our)?\s*(?:brand\s+)?new\s+"
            rf"(?:{ASSET_NOUN_REGEX})s?\b"
            rf"|\bnew\s+(?:{ASSET_NOUN_REGEX})s?\b"
            rf"|\badd\s+(?:a|an)?\s*(?:new\s+)?(?:{ASSET_NOUN_REGEX})s?\b",
            re.I,
        ),
    ),
    ("list_reminders", re.compile(r"\breminders\b|\bupcoming\b|\boverdue\b|\bwhat(?:'s| is) due\b", re.I)),
    ("warranty", re.compile(r"\bwarrant(?:y|ies)\b|\bunder warranty\b|\bcovered\b|\bguarantee\b", re.I)),
    ("list_assets", re.compile(r"\bappliances\b|\bassets\b|\binventory\b|\bwhat do i have\b|\bmy stuff\b", re.I)),
)

SERVICE_KEYWORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bwashing machine\b|\bwasher\b", re.I), "washing_machine"),
    (re.compile(r"\bfridge\b|\brefrigerator\b|\bfreezer\b", re.I), "refrigeration"),
    (re.compile(r"\bboiler\b|\bheating\b|\bradiator\b", re.I), "heating"),
    (re.compile(r"\bleak\b|\bplumb|\bpipe\b|\btap\b", re.I), "plumbing"),
    (re.compile(r"\belectric|\bwiring\b|\bsocket\b", re.I), "electrical"),
    (re.compile(r"\bmower\b|\bgarden\b|\blawn\b", re.I), "garden"),
)

ASSET_SYNONYMS: dict[str, str] = {
    "washer": "washing machine",
    "washing-machine": "washing machine",
    "fridge": "fridge freezer",
    "dish-washer": "dishwasher",
    "air-con": "air conditioner",
}

MAX_MESSAGE_LENGTH = 500


def _asset_label(record: dict[str, Any]) -> str:
    """Readable label for an asset: "Washing Machine (AquaLine AL-7200)"."""
    name = str(record.get("name") or "this item")
    brand = str(record.get("brand") or "").strip()
    model = str(record.get("model") or "").strip()
    detail = " ".join(part for part in (brand, model) if part)
    return f"{name} ({detail})" if detail else name


@dataclass
class ConversationState:
    """What the assistant remembers between turns of one conversation."""

    last_asset_id: str | None = None
    last_event_id: str | None = None
    last_service_category: str | None = None


@dataclass
class Card:
    """A UI card rendered next to the assistant reply."""

    type: str
    id: str
    title: str
    is_demo: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "is_demo": self.is_demo,
            **self.payload,
        }


@dataclass
class AssistantTurn:
    """The full result of one assistant turn."""

    reply: str
    cards: list[Card] = field(default_factory=list)
    tool_trace: list[ToolCallRecord] = field(default_factory=list)
    summary_provider: str = PROVIDER_DETERMINISTIC
    follow_up: str | None = None
    intent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "cards": [card.to_dict() for card in self.cards],
            "tool_trace": [record.to_dict() for record in self.tool_trace],
            "summary_provider": self.summary_provider,
            "follow_up": self.follow_up,
            "intent": self.intent,
        }


class Orchestrator:
    """Runs one assistant turn against the MCP server."""

    def __init__(
        self,
        mcp: MCPClientManager,
        settings: Settings,
        summary_provider: SummaryProvider | None = None,
    ) -> None:
        self.mcp = mcp
        self.settings = settings
        self.summary_provider = summary_provider
        self._conversations: dict[str, ConversationState] = {}

    def _state(self, conversation_id: str | None) -> ConversationState:
        return self._conversations.setdefault(conversation_id or "default", ConversationState())

    # -- helpers -----------------------------------------------------------

    async def _call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call an MCP tool, recording the trace entry."""
        payload, record = await self.mcp.call_tool(name, arguments)
        self._trace.append(record)
        return payload

    async def _load_assets(self) -> list[dict[str, Any]]:
        payload = await self._call("list_assets", {"limit": 100})
        assets = payload.get("assets") or []
        return [item for item in assets if isinstance(item, dict)]

    def _resolve_asset(
        self, message: str, assets: list[dict[str, Any]], state: ConversationState | None = None
    ) -> dict[str, Any] | None:
        """Pick the asset the message is about. Returns ``None`` when unclear."""
        text = message.lower()
        best: tuple[int, dict[str, Any]] | None = None

        for asset in assets:
            name = str(asset.get("name") or "")
            brand = str(asset.get("brand") or "")
            score = 0
            if name and name.lower() in text:
                score = 100
            elif brand and brand.lower() in text:
                score = 60
            else:
                tokens = [token for token in re.split(r"\W+", name.lower()) if len(token) > 2]
                matched = [token for token in tokens if token in text]
                if matched:
                    score = 40 + len(matched)
            if score and (best is None or score > best[0]):
                best = (score, asset)

        if best is not None:
            return best[1]

        # Fall back to synonyms ("washer" -> "washing machine").
        for synonym, target in ASSET_SYNONYMS.items():
            if re.search(rf"\b{re.escape(synonym)}\b", text):
                for asset in assets:
                    if str(asset.get("name", "")).lower() == target:
                        return asset

        # Fall back to the item the conversation was already about.
        if state is not None and state.last_asset_id:
            for asset in assets:
                if asset.get("asset_id") == state.last_asset_id:
                    return asset
        return None

    def _service_category(self, message: str) -> str:
        for pattern, category in SERVICE_KEYWORDS:
            if pattern.search(message):
                return category
        return "appliance_repair"

    # -- entry point -------------------------------------------------------

    async def handle(self, message: str, conversation_id: str | None = None) -> AssistantTurn:
        """Run one assistant turn."""
        self._trace: list[ToolCallRecord] = []
        text = (message or "").strip()
        if not text:
            return AssistantTurn(
                reply="Tell me what you would like to check - for example, whether an appliance is still under warranty.",
                intent="empty",
            )
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH]

        intent = self._detect_intent(text)
        state = self._state(conversation_id)

        handlers = {
            "warranty": self._handle_warranty,
            "list_assets": self._handle_list_assets,
            "list_reminders": self._handle_list_reminders,
            "maintenance_history": self._handle_history,
            "log_event": self._handle_log_event,
            "add_asset": self._handle_add_asset,
            "create_reminder": self._handle_create_reminder,
            "technician_brief": self._handle_brief,
            "service_handoff": self._handle_handoff,
            "demo_slots": self._handle_slots,
        }

        try:
            handler = handlers.get(intent, self._handle_unknown)
            turn = await handler(text, state)
        except HomeOpsError as exc:
            turn = AssistantTurn(
                reply=(
                    "The HomeOps MCP server could not complete that request, so I could not check the records. "
                    f"Details: {exc.message}"
                ),
                intent=intent,
                tool_trace=[record.to_dict() for record in self._trace],
            )
            return turn

        turn.tool_trace = self._trace
        turn.intent = intent
        return turn

    def _detect_intent(self, text: str) -> str:
        for intent, pattern in INTENT_PATTERNS:
            if pattern.search(text):
                return intent
        return "unknown"

    # -- intents -----------------------------------------------------------

    async def _handle_unknown(self, text: str, state: ConversationState) -> AssistantTurn:
        assets = await self._load_assets()
        names = ", ".join(str(asset.get("name")) for asset in assets[:6])
        return AssistantTurn(
            reply=(
                "I can help with household maintenance records. Try one of these:\n"
                "- \"Is my washing machine still under warranty?\"\n"
                "- \"I bought a new fridge\"\n"
                "- \"Remind me to check the boiler before it expires\"\n"
                "- \"Has the washing machine leaked before?\"\n"
                "- \"Prepare a brief for the technician\"\n"
                "- \"Help me contact a technician\"\n\n"
                f"Records I can see: {names}."
            )
        )

    async def _handle_list_assets(self, text: str, state: ConversationState) -> AssistantTurn:
        assets = await self._load_assets()
        if not assets:
            return AssistantTurn(reply="HomeOps has no household assets stored yet.")
        lines = [
            f"- {_asset_label(asset)}"
            f" - warranty {asset.get('warranty_status')} - {asset.get('location') or 'location unknown'}"
            for asset in assets
        ]
        demo_note = "\n\nThese are fictional demo records." if any(asset.get("is_demo") for asset in assets) else ""
        return AssistantTurn(
            reply="Here is the household inventory:\n" + "\n".join(lines) + demo_note,
            cards=[
                Card(
                    type="asset",
                    id=str(asset.get("asset_id")),
                    title=str(asset.get("name")),
                    is_demo=bool(asset.get("is_demo")),
                    payload={"warranty_status": asset.get("warranty_status")},
                )
                for asset in assets
            ],
        )

    async def _handle_warranty(self, text: str, state: ConversationState) -> AssistantTurn:
        assets = await self._load_assets()
        asset = self._resolve_asset(text, assets, state)
        if asset is None:
            return AssistantTurn(
                reply=(
                    "Which item should I check? HomeOps currently tracks: "
                    + ", ".join(str(item.get("name")) for item in assets)
                    + "."
                ),
                follow_up="Tell me the item name, for example \"is my washing machine still under warranty?\".",
            )
        state.last_asset_id = str(asset["asset_id"])

        detail = await self._call("get_asset_details", {"asset_id": asset["asset_id"]})
        info = detail.get("detail", {})
        warranty = info.get("warranty", {})
        record = info.get("asset", {})

        status = str(warranty.get("status", "unknown"))
        end = warranty.get("warranty_end")
        days = warranty.get("days_remaining")
        basis = str(warranty.get("basis_note", ""))

        label = _asset_label(record)

        if status == "unknown" or not end:
            reply = (
                f"{label} has no warranty end date stored in HomeOps, so its warranty "
                "status is unknown. Add the warranty end date from the receipt or the manufacturer's "
                "policy to get a useful answer."
            )
        else:
            remaining = f" That is {days} day(s) from today." if isinstance(days, int) else ""
            reply = (
                f"Based on the dates saved in HomeOps, {label} "
                f"has a warranty recorded as ending on {end} - marked as {status.replace('_', ' ')}.{remaining} "
                f"{basis} Source record: {asset['asset_id']}"
                + (" (fictional demo record)." if info.get("is_demo") else ".")
            )

        return AssistantTurn(
            reply=reply,
            cards=[
                Card(
                    type="asset",
                    id=str(asset["asset_id"]),
                    title=str(record.get("name")),
                    is_demo=bool(info.get("is_demo")),
                    payload={"warranty": warranty, "asset": record},
                )
            ],
        )

    async def _handle_list_reminders(self, text: str, state: ConversationState) -> AssistantTurn:
        payload = await self._call("list_reminders", {"limit": 50})
        reminders = payload.get("reminders") or []
        if not reminders:
            return AssistantTurn(reply="There are no reminders stored in HomeOps right now.")

        lines = []
        for reminder in reminders:
            marker = "DUE" if reminder.get("is_overdue") else str(reminder.get("status", "")).upper()
            asset = reminder.get("asset_name") or "no asset"
            lines.append(
                f"- [{marker}] {reminder.get('title')} - due {reminder.get('due_at')} ({reminder.get('timezone')}) - {asset}"
            )
        return AssistantTurn(
            reply="Reminders in HomeOps:\n" + "\n".join(lines),
            cards=[
                Card(
                    type="reminder",
                    id=str(reminder.get("reminder_id")),
                    title=str(reminder.get("title")),
                    is_demo=bool(reminder.get("is_demo")),
                    payload={
                        "due_at": reminder.get("due_at"),
                        "status": reminder.get("status"),
                        "is_overdue": reminder.get("is_overdue"),
                    },
                )
                for reminder in reminders
            ],
        )

    async def _handle_history(self, text: str, state: ConversationState) -> AssistantTurn:
        assets = await self._load_assets()
        asset = self._resolve_asset(text, assets, state)
        if asset is not None:
            state.last_asset_id = str(asset["asset_id"])

        arguments: dict[str, Any] = {"limit": 10}
        if asset is not None:
            arguments["asset_id"] = asset["asset_id"]

        query = self._extract_history_query(text)
        if query:
            arguments["query"] = query

        payload = await self._call("search_maintenance_history", arguments)
        events = payload.get("events") or []

        if not events:
            scope = asset["name"] if asset else "your records"
            return AssistantTurn(
                reply=(
                    f"I did not find a matching maintenance record for {scope} in HomeOps. "
                    "That means there is no stored history - not that nothing happened."
                )
            )

        lines = []
        for event in events:
            occurred = event.get("occurred_at") or event.get("created_at") or "time not recorded"
            outcome = f" - outcome: {event.get('outcome')}" if event.get("outcome") else ""
            lines.append(
                f"- {occurred}: {event.get('description')} ({event.get('event_type')}){outcome} [record {event.get('event_id')}]"
            )
        return AssistantTurn(
            reply="Yes - HomeOps has these related records:\n" + "\n".join(lines),
            cards=[
                Card(
                    type="maintenance_event",
                    id=str(event.get("event_id")),
                    title=str(event.get("description"))[:80],
                    is_demo=bool(event.get("is_demo")),
                    payload={"occurred_at": event.get("occurred_at"), "event_type": event.get("event_type")},
                )
                for event in events
            ],
        )

    def _extract_history_query(self, text: str) -> str | None:
        """Pull a useful search term out of a 'has this happened before' question."""
        match = re.search(r"\b(has|have)\s+(?:this|it|we)\s+(?:happened|leaked|broken|failed)\b(.*)", text, re.I)
        if match:
            remainder = match.group(2).strip(" ?!.")
            return remainder or None
        match = re.search(r"\b(?:before|previously)\b\s*(.*)", text, re.I)
        if match:
            remainder = match.group(1).strip(" ?!.")
            return remainder or None
        return None

    async def _handle_log_event(self, text: str, state: ConversationState) -> AssistantTurn:
        assets = await self._load_assets()
        asset = self._resolve_asset(text, assets, state)
        if asset is not None:
            state.last_asset_id = str(asset["asset_id"])

        description = self._clean_description(text)
        arguments: dict[str, Any] = {
            "event_type": "issue",
            "description": description,
            "source_type": "user_entered",
        }
        if asset is not None:
            arguments["asset_id"] = asset["asset_id"]

        payload = await self._call("log_maintenance_event", arguments)
        event_id = payload.get("event_id")

        if asset is None:
            reply = (
                f"Logged your report as a new maintenance record ({event_id}). "
                "Tell me which item it concerns and I will link it to the right asset."
            )
        else:
            reply = (
                f"Logged a new issue for {asset['name']}: \"{description}\". "
                f"Record ID {event_id}, source: entered by you."
            )
        return AssistantTurn(
            reply=reply,
            cards=[
                Card(
                    type="maintenance_event",
                    id=str(event_id),
                    title=description[:80],
                    is_demo=False,
                    payload={"asset_id": asset.get("asset_id") if asset else None},
                )
            ],
        )

    def _clean_description(self, text: str) -> str:
        cleaned = re.sub(
            r"^\s*(please\s+)?(can you\s+)?(log|record|add|report)\s+(that\s+)?", "", text, flags=re.I
        ).strip()
        if not cleaned:
            cleaned = text.strip()
        return cleaned[:500]

    # -- add asset ---------------------------------------------------------

    _BRAND_STOPWORDS = {
        "a",
        "an",
        "the",
        "my",
        "our",
        "their",
        "his",
        "her",
        "this",
        "that",
        "new",
        "brand",
        "i",
        "we",
        "just",
        "recently",
        "bought",
        "purchased",
        "got",
        "received",
        "installed",
    }

    def _extract_asset(self, text: str) -> tuple[str, str, AssetCategory] | None:
        """Map a free-text item to a canonical name and category."""
        lower = text.lower()
        for noun, name, category in ASSET_NOUNS:
            if re.search(rf"\b{re.escape(noun)}s?\b", lower):
                return noun, name, category
        return None

    def _extract_brand(self, text: str, noun: str) -> str | None:
        """Read a brand only when the user typed it as a capitalised word."""
        match = re.search(
            rf"\b([A-Z][A-Za-z0-9&'.-]{{1,30}})\s+{re.escape(noun)}\b", text
        )
        if match is None:
            return None
        candidate = match.group(1).strip()
        if candidate.lower() in self._BRAND_STOPWORDS:
            return None
        return candidate

    def _extract_purchase_date(self, text: str) -> str | None:
        """Read an explicit purchase date; never guess one."""
        match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if match:
            try:
                return date.fromisoformat(match.group(1)).isoformat()
            except ValueError:
                return None
        today = today_in(self.settings.household_timezone)
        if re.search(r"\byesterday\b", text, re.I):
            return (today - timedelta(days=1)).isoformat()
        if re.search(r"\btoday\b", text, re.I):
            return today.isoformat()
        return None

    async def _handle_add_asset(self, text: str, state: ConversationState) -> AssistantTurn:
        matched = self._extract_asset(text)
        if matched is None:
            return AssistantTurn(
                reply=(
                    "I can add that item, but I need to know what it is. "
                    "For example: \"I bought a new washing machine\" or \"add a new boiler\"."
                ),
                follow_up="What kind of item did you buy?",
            )

        noun, name, category = matched
        brand = self._extract_brand(text, noun)
        purchase = self._extract_purchase_date(text)

        arguments: dict[str, Any] = {
            "name": name,
            "category": str(category),
            "timezone": self.settings.household_timezone,
            "source_type": "user_entered",
        }
        if brand:
            arguments["brand"] = brand
        if purchase:
            arguments["purchase_date"] = purchase

        payload = await self._call("create_asset", arguments)
        detail = payload.get("detail") or {}
        asset = detail.get("asset") or {}
        asset_id = str(asset.get("asset_id") or "")
        if asset_id:
            state.last_asset_id = asset_id

        label = _asset_label(asset) if asset else name
        purchase_note = (
            f"Purchase date recorded as {purchase}. "
            if purchase
            else "No purchase date was supplied, so it stays unknown. "
        )
        reply = (
            f"Added {label} to HomeOps as a new asset (ID {asset_id}). "
            f"{purchase_note}"
            "No warranty dates are stored, so the warranty status is unknown."
        )
        return AssistantTurn(
            reply=reply,
            cards=[
                Card(
                    type="asset",
                    id=asset_id,
                    title=str(asset.get("name") or name),
                    is_demo=bool(asset.get("is_demo")),
                    payload={
                        "warranty_status": (detail.get("warranty") or {}).get("status", "unknown"),
                        "category": asset.get("category"),
                    },
                )
            ],
        )

    async def _handle_create_reminder(self, text: str, state: ConversationState) -> AssistantTurn:
        assets = await self._load_assets()
        asset = self._resolve_asset(text, assets, state)
        if asset is not None:
            state.last_asset_id = str(asset["asset_id"])

        due_at = parse_due_datetime(text, self.settings.household_timezone)
        warranty_end = None
        if asset is not None:
            detail = await self._call("get_asset_details", {"asset_id": asset["asset_id"]})
            warranty_end = (detail.get("detail", {}).get("warranty", {}) or {}).get("warranty_end")
        else:
            # If user says "expires"/"warranty" without naming asset, try to pick the asset with expiring warranty
            lower = text.lower()
            if any(k in lower for k in ("expire", "warrant", "guarantee")):
                # look up details for assets with expiring/expiring soon
                candidates = []
                for a in assets:
                    try:
                        detail = await self._call("get_asset_details", {"asset_id": a["asset_id"]})
                        w = (detail.get("detail", {}).get("warranty", {}) or {})
                        status = str(w.get("status") or "")
                        if status in ("expiring_soon", "expiring", "active", "expires_soon") or w.get("warranty_end"):
                            candidates.append((a, w))
                    except Exception:
                        continue
                if len(candidates) == 1:
                    asset, w = candidates[0]
                    state.last_asset_id = str(asset["asset_id"])
                    warranty_end = w.get("warranty_end")
                elif candidates:
                    # prefer expiring soon
                    for a, w in candidates:
                        if str(w.get("status")) == "expiring_soon":
                            asset, warranty_end = a, w.get("warranty_end")
                            state.last_asset_id = str(asset["asset_id"])
                            break
                    if asset is None and candidates:
                        asset, w = candidates[0]
                        state.last_asset_id = str(asset["asset_id"])
                        warranty_end = w.get("warranty_end")

        lead_days = self._lead_days_before(text)
        if due_at is None and asset is not None and warranty_end:
            # "Remind me a month before it expires" -> derive the date from the stored warranty end.
            end_date = datetime.fromisoformat(str(warranty_end))
            tz = self.settings.tzinfo
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=tz)
            due_at = datetime.combine(
                end_date.date() - timedelta(days=lead_days),
                end_date.time().replace(tzinfo=tz) if end_date.time().tzinfo is None else end_date.time(),
                tzinfo=tz,
            )
            # ensure offset present
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=tz)

        if due_at is None:
            return AssistantTurn(
                reply=(
                    "I can create that reminder, but I need a due date so I do not guess one. "
                    "For example: \"remind me to check the washing machine on 2026-12-01 at 09:00\" "
                    "or \"remind me in two weeks\"."
                ),
                follow_up="What date and time should the reminder be due?",
            )

        title = self._reminder_title(text, asset)
        arguments: dict[str, Any] = {
            "title": title,
            "due_at": due_at.isoformat(),
            "timezone": self.settings.household_timezone,
        }
        if asset is not None:
            arguments["asset_id"] = asset["asset_id"]

        payload = await self._call("create_reminder", arguments)
        reminder_id = payload.get("reminder_id")

        if warranty_end and due_at.date().isoformat() == (
            datetime.fromisoformat(str(warranty_end)).date() - timedelta(days=lead_days)
        ).isoformat():
            reason = (
                f"That is {lead_days} day(s) before the warranty end date saved for {asset['name']} "
                f"({warranty_end})."
            )
        else:
            reason = ""

        reply = (
            f"Reminder saved: \"{title}\" due {due_at.strftime('%Y-%m-%d %H:%M')} "
            f"({self.settings.household_timezone}). {reason}Reminder ID {reminder_id}."
        ).strip()
        return AssistantTurn(
            reply=reply,
            cards=[
                Card(
                    type="reminder",
                    id=str(reminder_id),
                    title=title,
                    is_demo=bool(payload.get("is_demo")),
                    payload={"due_at": payload.get("due_at"), "status": payload.get("status")},
                )
            ],
        )

    def _reminder_title(self, text: str, asset: dict[str, Any] | None) -> str:
        title = re.sub(
            r"^\s*(please\s+)?(can you\s+)?remind me\s*(to|that|about)?\s*", "", text, flags=re.I
        ).strip(" .?!")
        if not title:
            title = f"Maintenance reminder for {asset['name']}" if asset else "Maintenance reminder"
        if asset and asset["name"].lower() not in title.lower():
            title = f"{title} ({asset['name']})"
        return title[:200]

    def _lead_days_before(self, text: str) -> int:
        """How long before the warranty end the reminder should fire."""
        if re.search(r"\bweek before\b|\ba week before\b", text, re.I):
            return 7
        if re.search(r"\bmonth before\b|\ba month before\b", text, re.I):
            return 30
        if re.search(r"\btwo weeks before\b", text, re.I):
            return 14
        return 30

    async def _handle_brief(self, text: str, state: ConversationState) -> AssistantTurn:
        assets = await self._load_assets()
        asset = self._resolve_asset(text, assets, state)
        if asset is not None:
            state.last_asset_id = str(asset["asset_id"])

        arguments: dict[str, Any] = {"include_history": True}
        event_id = self._extract_event_id(text)
        if event_id:
            arguments["event_id"] = event_id
            state.last_event_id = event_id
        elif asset is not None:
            arguments["asset_id"] = asset["asset_id"]
        elif state.last_event_id:
            arguments["event_id"] = state.last_event_id
        else:
            return AssistantTurn(
                reply=(
                    "Which item should the brief cover? HomeOps currently tracks: "
                    + ", ".join(str(item.get("name")) for item in assets)
                    + "."
                ),
                follow_up="Tell me the item name, for example \"prepare a brief for the washing machine\".",
            )

        payload = await self._call("get_technician_brief", arguments)
        brief = payload

        provider = PROVIDER_DETERMINISTIC
        summary_text = str(brief.get("summary") or "")
        if self.summary_provider is not None and self.summary_provider.name != PROVIDER_DETERMINISTIC:
            summary_text, provider = self.summary_provider.summarize(brief)
            brief = {**brief, "summary": summary_text, "summary_provider": provider}

        facts = brief.get("facts") or []
        unknowns = brief.get("unknowns") or []
        record_ids = brief.get("record_ids") or []

        lines = [f"- {fact.get('label')}: {fact.get('value')}" for fact in facts]
        reply = (
            f"Technician brief - {brief.get('title')}\n"
            f"{summary_text}\n\n"
            + "\n".join(lines)
            + ("\n\nStill unknown: " + ", ".join(unknowns) if unknowns else "")
            + f"\n\nSource records: {', '.join(str(r) for r in record_ids)}"
            + ("\nSummary provider: Bedrock." if provider == "bedrock" else "\nSummary provider: deterministic template.")
        )
        return AssistantTurn(
            reply=reply,
            cards=[
                Card(
                    type="technician_brief",
                    id=str(brief.get("asset_id") or brief.get("event_id") or "brief"),
                    title=str(brief.get("title")),
                    is_demo=bool(brief.get("is_demo")),
                    payload={
                        "facts": facts,
                        "unknowns": unknowns,
                        "record_ids": record_ids,
                        "summary": summary_text,
                    },
                )
            ],
            summary_provider=provider,
        )

    def _extract_event_id(self, text: str) -> str | None:
        match = re.search(r"\bevt_[a-z0-9]+\b", text)
        return match.group(0) if match else None

    async def _handle_handoff(self, text: str, state: ConversationState) -> AssistantTurn:
        assets = await self._load_assets()
        asset = self._resolve_asset(text, assets, state)
        if asset is not None:
            state.last_asset_id = str(asset["asset_id"])
        category = self._service_category(text)
        state.last_service_category = category

        arguments: dict[str, Any] = {"service_category": category}
        if asset is not None:
            arguments["asset_id"] = asset["asset_id"]
        event_id = self._extract_event_id(text)
        if event_id:
            arguments["event_id"] = event_id
            state.last_event_id = event_id

        payload = await self._call("prepare_service_handoff", arguments)
        actions = payload.get("actions") or []
        provider = payload.get("provider") or {}
        message = payload.get("message_draft") or ""

        action_lines = []
        for action in actions:
            recipient = action.get("recipient")
            target = f" to {recipient}" if recipient else ""
            action_lines.append(f"- {action.get('label')}{target}")

        unavailable = payload.get("unavailable_actions") or []
        reply = (
            f"Prepared a handoff for {category.replace('_', ' ')}"
            + (f" with {provider.get('name')}" if provider.get("name") else "")
            + ".\n"
            + ("\n".join(action_lines) if action_lines else "- No outbound actions are available.")
            + ("\n\nNot available for this provider: " + ", ".join(unavailable) if unavailable else "")
            + "\n\n"
            + payload.get("disclaimer", "")
        )
        if message:
            reply += "\n\nMessage draft:\n" + message

        return AssistantTurn(
            reply=reply,
            cards=[
                Card(
                    type="handoff",
                    id=str(provider.get("provider_id") or "handoff"),
                    title=f"Handoff - {category.replace('_', ' ')}",
                    is_demo=bool(provider.get("is_demo")),
                    payload={
                        "actions": actions,
                        "unavailable_actions": unavailable,
                        "message_draft": message,
                        "provider": provider,
                        "disclaimer": payload.get("disclaimer"),
                    },
                )
            ],
        )

    async def _handle_slots(self, text: str, state: ConversationState) -> AssistantTurn:
        category = self._service_category(text)
        payload = await self._call("list_demo_service_slots", {"service_category": category, "limit": 10})
        slots = payload.get("slots") or []
        if not slots:
            return AssistantTurn(
                reply=(
                    f"There are no demo slots stored for {category.replace('_', ' ')}. "
                    "That is a valid answer - the demo only ships fictional slots for a few services."
                )
            )
        lines = [
            f"- {slot.get('slot_id')}: {slot.get('starts_at')} to {slot.get('ends_at')} "
            f"({slot.get('provider_id')})"
            for slot in slots
        ]
        reply = (
            "Demo slots (fictional - they do not represent real availability):\n"
            + "\n".join(lines)
            + "\n\nPick one and I will draft a simulated request. It stays pending until you confirm it."
        )
        return AssistantTurn(
            reply=reply,
            cards=[
                Card(
                    type="service_slot",
                    id=str(slot.get("slot_id")),
                    title=f"{slot.get('starts_at')}",
                    is_demo=True,
                    payload={"provider_id": slot.get("provider_id"), "service_type": slot.get("service_type")},
                )
                for slot in slots
            ],
        )
