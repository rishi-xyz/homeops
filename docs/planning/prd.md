# HomeOps — Product Requirements Document (PRD)

**Version:** 1.0 — Hackathon MVP  
**Date:** October 21, 2026  
**Primary target:** Laptop-first demo for the Amazon Developer Hackathon Alexa+ track

## 1. Product vision

HomeOps is a persistent household-maintenance assistant exposed as MCP tools. It stores appliance and fixture details, warranties, service history and reminders, then helps people choose the next action when maintenance is due or something breaks.

The hackathon experience is a web-based Alexa+-style simulation backed by a real self-hosted MCP server. It is not a live Alexa+ add-on deployment and does not require Alexa hardware.

## 2. Problem statement

Household maintenance is hard to manage because essential details are scattered and reminders are disconnected from service history. Users often cannot quickly answer:

- Is this item under warranty?
- What repair happened last time?
- When is routine service due?
- What information should I give a technician?
- How do I contact or book a suitable provider?

HomeOps should answer these questions from saved information and make the next step easier without claiming actions that have not actually occurred.

## 3. Target users and jobs to be done

### Primary persona

A homeowner or renter maintaining a small set of household appliances, who wants a voice-friendly way to recall details and organize maintenance.

### Jobs

- “When is this appliance's warranty ending?”
- “Remind me to service it before the due date.”
- “Have we had this issue before?”
- “Prepare a useful summary for a technician.”
- “Help me contact a service provider.”
- “Show the service history and what is still outstanding.”

## 4. Goals and non-goals

### Goals

- Demonstrate useful persistence between conversations.
- Provide structured, source-grounded household records.
- Implement a working MCP server and actual MCP client calls in the demo path.
- Deliver one polished end-to-end maintenance workflow.
- Provide a user-controlled bridge from internal records to real provider channels.
- Integrate Amazon Bedrock at runtime if credentials and model access are available, to pursue the AWS Builder mini-challenge.

### Non-goals

- Claiming a real Alexa+ device/platform connection.
- Confirming real bookings without a provider confirmation.
- Automatically sending WhatsApp messages or emails in the MVP.
- Scraping or automating arbitrary provider booking websites.
- Using sensors to diagnose equipment or detect hazards.
- Building a full marketplace, payment system, mobile app or production multi-tenant account platform.

## 5. MVP scope and priorities

### P0 — Hackathon qualification and basic reliability

1. Self-hosted MCP server over Streamable HTTP using the official MCP SDK.
2. Runtime MCP client integration from the app backend.
3. SQLite schema and seeded demo household.
4. A browser-based Alexa+-style simulation.
5. Tool call visibility, setup documentation, tests, public repository/license and short demo video.

### P1 — Core HomeOps value

1. Asset inventory and detail records.
2. Warranty and maintenance date tracking.
3. Create/list reminders and show upcoming/overdue reminders.
4. Log maintenance issues and search prior events.
5. Technician brief generated from records.
6. External provider handoff links and a simulated booking flow.

### P2 — AWS and polish

1. Amazon Bedrock-powered summary generation behind an optional adapter.
2. Deterministic fallback when Bedrock is not configured or fails.
3. A polished activity panel, empty states and responsive layout.
4. Optional browser notification while the web app is open.

## 6. Functional requirements

### FR-01: Household inventory

The user can list assets and open a detail view containing name, category, location, brand/model, purchase date, warranty dates, manual/receipt references and source/provenance. Fields that are unknown remain explicitly unknown.

**Acceptance:** opening an asset shows exactly the values stored in the database and a visible demo label for seeded records.

### FR-02: Warranty status

HomeOps may classify a recorded warranty as active, expiring soon, expired or unknown by comparing stored dates with the current date in the household timezone. This is an informational calculation, not verification of manufacturer coverage. Terms, exclusions and proof-of-purchase requirements may affect real claims.

**Acceptance:** no warranty status is stated as verified unless the source has been verified; otherwise the UI uses “based on saved dates.”

### FR-03: Reminders

Users can create, list, complete, snooze or delete a reminder related to an asset or maintenance event. A reminder includes title, due time/date, timezone, recurrence if supported, status and source. The dashboard shows upcoming and overdue items. The backend checks due reminders and the UI surfaces due items while open; after a restart, due state is calculated from persisted dates.

**MVP limitation:** do not promise OS-level push notifications when the app/backend is closed. The hackathon demo can show due reminders in the dashboard and use an in-app notification while running.

### FR-04: Maintenance and incident history

Users can log an issue, repair, servicing event or outcome and search history by asset, event type, date range or text. Each event keeps event/occurred time separate from record-created time.

**Acceptance:** history search reports “no matching record” when there is no record; it never invents prior work.

### FR-05: Technician brief

HomeOps combines asset details, known warranty dates, current issue, relevant prior incidents, recorded troubleshooting, and missing information into a concise brief. Every factual detail must be traceable to stored record IDs. The LLM, if used, can phrase and organize content but cannot add facts.

### FR-06: Provider discovery and handoff

HomeOps provides one or more safe next actions:

- Google Maps search for a service category and locality.
- WhatsApp click-to-chat with a prefilled draft if a valid provider number is known.
- Phone (`tel:`) or email (`mailto:`) action when details exist.
- An official provider booking page if a verified URL is stored.
- Simulated provider/slot data for the deterministic hackathon demo.

The app must not report that a message has been sent or booking confirmed merely because a link was generated or opened. External actions are completed by the user unless a real provider API integration is later added.

### FR-07: Simulated booking

Users may select a fictional service slot and create a pending request. The UI states “Demo booking — no real provider contacted.” A visible confirmation click changes the record to `confirmed_demo`. This is a simulation only.

### FR-08: Persistent tool execution and visible trace

The assistant-style UI shows which MCP tool was called, whether it succeeded, and a short result summary. Main interaction paths call the running MCP server using an MCP client. UI-only mock traces do not satisfy this requirement.

### FR-09: AWS Bedrock (conditional)

When configured, the backend can send a minimal structured set of demo records to Amazon Bedrock to produce a summary. Input must be bounded and schema-backed. The service response is treated as untrusted text and checked against source records. The default model adapter may be disabled for deterministic development.

**AWS Builder acceptance:** a real Bedrock Runtime invocation succeeds from the running application, the code path is present in the repository, configuration is documented without secrets, and the submission's tool feedback describes the actual use. Mentioning Bedrock in docs alone is insufficient.

### FR-10: Demo reset

A development-only control resets fictional seed data after confirmation. It must not be exposed publicly without authentication.

## 7. Main demo journey

1. User asks whether a washing machine is under warranty.
2. HomeOps displays warranty dates and their source/status.
3. User asks for a reminder before expiry; the reminder is persisted.
4. User reports a leak and asks whether it happened before; HomeOps retrieves prior incident records.
5. User asks for help finding service. HomeOps creates a technician brief, offers a Maps search/provider handoff, and optionally shows fictional slots.
6. If a demo slot is chosen, the request remains pending until the user confirms. The UI labels the booking as simulated.

## 8. User experience requirements

- Calm, clear, responsive interface inspired by conversational assistants, without falsely copying or claiming to be the Alexa product UI.
- Text input and suggested prompts are sufficient; speech input/output is optional.
- Visible household context, maintenance timeline, reminders, and provider handoff cards.
- The UI distinguishes saved facts, user-entered content, demo records, model-generated wording and actual statuses.
- Explicit confirmation for simulated booking and any external action that would submit user data.
- Accessible keyboard focus, readable contrast, clear loading/error/empty states.

## 9. Privacy and trust requirements

- Seed data must be fictional and marked as such.
- Do not commit `.env`, credentials, user address/phone, real receipts, or private household data.
- External model calls send only the minimum required data; the demo should use synthetic data.
- Do not automatically send messages or book real services.
- Validate and constrain generated links; never let an LLM invent a destination URL that the backend blindly opens.
- Provide a clear explanation of what is stored and what an external provider/model receives.

## 10. Success metrics for the hackathon

- MCP client can initialize, list tools and call the server over Streamable HTTP.
- Core user journey completes from clean reset without a paid account or live provider API.
- At least the main records and reminders persist across reloads.
- No unsupported provider-sent or booking-confirmed claims appear in the UI.
- A source-linked technician brief can be generated from stored records.
- Public source repository, license, setup steps and English demo video under three minutes are ready before submission.

## 11. Future roadmap (post-hackathon)

- OAuth accounts and multiple households.
- Document/receipt import with user review and source extraction.
- Calendar integrations and reliable push/email notification delivery.
- Provider-specific booking APIs and status callbacks where available and authorized.
- Optional smart-home/device events and integrations.
- Encryption/key management, formal retention policy, auditing and deployment hardening.
