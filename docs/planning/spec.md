# HomeOps — Technical Specification

**Version:** 1.0 — Hackathon MVP  
**Scope:** household inventory, warranty tracking, reminders, maintenance history, provider handoffs, simulated booking, MCP server, Alexa+-style simulator, optional Amazon Bedrock summary generation.

## 1. Product modes

- **Demo mode:** fictional seeded home data and simulated service slots. Visible throughout the UI.
- **Real handoff mode:** user-entered records plus user-reviewed links to Google Maps, WhatsApp, phone, email or a stored provider booking page. Opening a link is not proof of send/booking.
- **Assistant simulation:** browser UI simulating a voice-assistant interaction. It is not a live Alexa+ device integration.

## 2. Data and timestamp rules

- All record IDs are stable unique IDs.
- Store timestamps in UTC or ISO-8601 with offset; store the household timezone for date-based reminders.
- Keep `occurred_at`/`reported_at` distinct from `created_at`.
- Missing purchase dates, warranty terms, provider details and event times must remain unknown. Do not ask an LLM to fill them.
- Records include a source/provenance type and `is_demo` flag.
- Warranty calculations are based on saved dates only; do not assert coverage is officially verified.

## 3. Functional requirements

### F1 — Asset inventory and warranty

List, filter and inspect household assets. Asset detail includes category, location, brand/model, purchase date, warranty start/end, manual/receipt references and linked maintenance events. Classify saved dates as active, expiring soon, expired or unknown with configurable “expiring soon” threshold (default 30 days).

**Acceptance:** UI says “based on saved dates” unless a warranty record has an explicit verified source. Unknown dates yield `unknown`, never an inferred date.

### F2 — Reminder lifecycle

Users can create, list, complete, snooze and cancel reminders. Fields: `reminder_id`, optional `asset_id`, title, `due_at`, timezone, status, optional recurrence/source event, created/completed timestamps and demo flag.

Status behavior:
- `pending`: due time is in the future.
- `due`: due time has passed and not completed/cancelled.
- `completed`: user marked complete.
- `snoozed`: user postponed to a new due time.
- `cancelled`: no longer active.

An implementation can compute `due` from date/status at query time rather than running an always-on scheduler. While the app is open, refresh/polling can show newly due reminders. Do not promise OS-level push when the server/browser is closed.

### F3 — Maintenance history

Log issue, inspection, routine service, repair or note. Search by asset, type, dates and query. The response includes event ID, asset ID, description, `occurred_at`, `created_at`, outcome, source and demo flag.

### F4 — Technician brief

Build a brief for a selected issue including asset/model, saved warranty information, current issue, relevant prior events and outcomes, known troubleshooting, missing details and record IDs. Any model-generated wording must be bounded by those records.

### F5 — Provider discovery and handoff

Offer supported external actions based on available fields:
- Maps search using service type + locality.
- WhatsApp prefilled message if valid phone number is available.
- Phone/email links if their contact data exists.
- Official booking URL only if supplied/stored and validated.
- Demo appointment slots in demo mode.

The handoff preview must display recipient, message contents and which fields will be included. The user chooses to open the link. The app tracks `handoff_opened` at most; it must not claim sent/accepted/confirmed.

### F6 — Simulated request and booking

A request must begin as `draft` or `awaiting_user_action`. A simulated slot can be confirmed only after a visible confirmation interaction. The final status must be `confirmed_demo`, and the UI must state that no real provider has been contacted.

### F7 — MCP runtime and trace

The server uses an official MCP SDK and Streamable HTTP. The application backend uses an MCP client to call it. On the primary assistant flow, tool calls cannot be mocked or bypass the MCP server. The UI displays tool names, success/failure and short results.

### F8 — Bedrock summary provider (optional challenge feature)

When `HOMEOPS_SUMMARY_PROVIDER=bedrock`, call the configured Amazon Bedrock Runtime model to summarize an evidence payload. When disabled/unavailable, fall back to a deterministic template. The UI or logs should make the provider used inspectable for the demo. Do not mark AWS Builder complete unless a real invocation succeeds.

## 4. MCP tool contracts

All schemas must be explicit, validate arguments, return structured data, and use bounded query/limit sizes. Errors should be useful and must not expose stack traces or secrets.

### `list_assets`

**Input:** optional `query`, optional `category`, optional `limit` (default 20, max 100).  
**Output:** `assets[]` with IDs, display names, category, location and `is_demo`.

### `get_asset_details`

**Input:** `asset_id`.  
**Output:** asset metadata, saved warranty/purchase dates, provenance, manual/receipt references and linked recent maintenance event IDs.  
**Error:** unknown asset ID.

### `search_maintenance_history`

**Input:** optional `asset_id`, `event_type`, `query`, `start_at`, `end_at`, `limit` (default 10, max 50).  
**Output:** matching events with `event_id`, `asset_id`, type, description, `occurred_at`, `created_at`, outcome, source and `is_demo`.  
**Errors:** invalid ID/date range/query size.

### `log_maintenance_event`

**Input:** `event_type`, `description`, optional `asset_id`, `occurred_at`, `outcome`, `location`, `source_type` from an allowlist.  
**Output:** created record and generated ID.  
**Rules:** user-reported events must not be labeled as sensor-detected.

### `create_reminder`

**Input:** `title`, `due_at`, `timezone`, optional `asset_id`, optional `source_event_id`, optional recurrence descriptor.  
**Output:** saved reminder and due state.  
**Rules:** validate timezone/date and asset/event references; reject impossible values and oversized titles.

### `list_reminders`

**Input:** optional `status`, `asset_id`, `from_at`, `to_at`, `limit` (default 20, max 100).  
**Output:** matching reminders ordered by due time, with computed `is_overdue` and demo flag.

### `complete_reminder`

**Input:** `reminder_id`.  
**Output:** updated reminder with `status=completed` and completion timestamp.  
**Rules:** idempotent for already completed reminders.

### `prepare_service_handoff`

**Input:** `issue_event_id` or short issue description, service category, locality, optional `provider_id`, optional preferred time, optional user-approved details to include.  
**Output:** technician brief, maps search URL, and available WhatsApp/phone/email/booking actions. Fields with no known values are omitted; do not create fake contact info.  
**Rules:** only build outbound message content for user preview; do not send it. Provider booking URLs must come from a validated stored provider record.

### `list_demo_service_slots`

**Input:** service category, optional preferred date and limit (max 20).  
**Output:** fictional provider labels, `slot_id`, start/end times and `is_demo=true`. Empty result is valid.

### `draft_demo_service_request`

**Input:** optional issue/event ID, `slot_id`, optional note.  
**Output:** request ID, selected slot, status `awaiting_user_action` and `is_demo=true`.  
**Rules:** slot must exist and be available; this tool does not confirm a booking.

### `confirm_demo_service_request`

**Input:** `request_id` and server-validated confirmation reference or a protected confirmation path.  
**Output:** status `confirmed_demo`, confirmation timestamp, `is_demo=true`.  
**Rules:** valid pending request required; idempotent; cannot create a real booking.

### `get_technician_brief`

**Input:** `event_id`, optional `include_history`.  
**Output:** structured brief sections, source record IDs and explicit unknowns.  
**Rules:** deterministic assembly is the default; optional Bedrock can rephrase/organize only the supplied facts.

## 5. Frontend API contracts

Frontend talks to FastAPI, not MCP directly.

### `GET /health`

Returns process status and safe dependency flags; no secrets.

### `POST /api/assistant/message`

Example request:

```json
{
  "message": "Is my washing machine still under warranty?",
  "conversation_id": "demo-session-1"
}
```

Example response shape:

```json
{
  "reply": "Based on the saved demo dates, the warranty is recorded as ending on 2026-12-15.",
  "cards": [{"type": "asset", "id": "asset_washer_01", "is_demo": true}],
  "tool_trace": [{"name": "get_asset_details", "status": "success", "record_ids": ["asset_washer_01"]}],
  "summary_provider": "deterministic"
}
```

The exact seed values may differ. The response must reflect real database contents and actual MCP tool results.

### `GET /api/assets`

Returns asset summaries for dashboard navigation.

### `GET /api/reminders`

Returns upcoming/due/overdue reminders with timezone-aware status.

### `POST /api/reminders`

Creates a reminder by invoking the MCP tool through an MCP client.

### `POST /api/handoff/prepare`

Returns a user-reviewable provider handoff card. It must not send messages automatically.

### `POST /api/demo-requests` and `POST /api/demo-requests/{id}/confirm`

Create and confirm simulated service requests through MCP. Confirmation must be explicit and idempotent.

### `POST /api/demo/reset`

Resets local demo data only; confirm before action and disable on an unauthenticated public deployment.

## 6. Deterministic intent routing

The MVP can use a simple allowlisted router for known intents:

- warranty / asset status → `list_assets` or `get_asset_details`
- “remind me” → `create_reminder` after due date/time is explicit
- “has this happened before” → `search_maintenance_history`
- report a repair/issue → `log_maintenance_event`
- find a technician → `prepare_service_handoff`
- prepare a technician brief → `get_technician_brief`
- demo booking → `list_demo_service_slots`, then draft and explicit confirmation

If intent or date is ambiguous, ask a follow-up rather than inventing details. Natural-language LLM routing is optional, and tool choice stays allowlisted.

## 7. Error and state handling

- Unknown asset/event/reminder/provider IDs return a structured not-found result.
- No matching record returns an empty list and clear message, not generated history.
- Invalid due dates/timezones are rejected with actionable messages.
- Provider has no phone/email/booking page: omit the unsupported action and still offer a Maps search if enough location data exists.
- External link cannot be opened: retain the draft and let the user copy its contents.
- Bedrock timeout/permission/model error: fall back to deterministic summary and mark provider status accordingly; never lose the underlying records.
- Duplicate reminder completion and demo booking confirmation are idempotent.

## 8. Security, privacy and non-functional requirements

- Keep servers local-only for the demo unless remote access is intentionally secured.
- No arbitrary command execution, unrestricted SQL, URL fetch, or model-generated link opening.
- Validate outbound destinations and encode query/message parameters.
- Secrets only in environment/standard credential chains; `.env` and local database ignored by Git.
- Use synthetic records for recordings and Bedrock calls.
- Bound response time, tool output sizes and result limits; handle errors without stack traces in the UI.
- Mark seeded records and simulated bookings prominently.

## 9. Required tests

1. Warranty date classification for active, expiring, expired and unknown cases.
2. Reminder create/list/complete/snooze and timezone edge cases.
3. Maintenance history search with a match and a no-match result.
4. Maps/WhatsApp/mailto/tel URL construction and parameter encoding.
5. Missing/invalid provider contact fields do not create fake actions.
6. MCP client can initialize/list/call tools over Streamable HTTP and required protocol version is verified.
7. API assistant flow actually invokes the MCP server.
8. Demo booking cannot reach `confirmed_demo` before explicit confirmation.
9. Technician brief fields correspond to stored record IDs and timestamps.
10. Bedrock fallback works without AWS credentials; opt-in real invocation smoke test is documented and run if AWS mini-challenge is claimed.

## 10. Hackathon qualification guardrail

The primary submission path is the Alexa+ MCP path: real MCP server over Streamable HTTP, runtime tool usage, clean source repository, and visible end-to-end demo. A browser simulation is also explicitly permitted by the rules. The project should not claim physical Alexa hardware or live Alexa+ onboarding.

AWS Builder is an optional second objective. Claim it only if Amazon Bedrock is genuinely called by the running application and documented in the submission feedback. If not, submit the Alexa+ track without claiming AWS Builder.
