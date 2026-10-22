# HomeOps — Idea

**Status:** Hackathon MVP definition  
**Primary track:** Alexa+ (self-hosted MCP server plus a browser-based Alexa+-style simulator)  
**Optional mini-challenge:** AWS Builder, only if the Amazon Bedrock integration is called successfully at runtime and documented  
**Planning date:** October 21, 2026  
**Hackathon deadline:** October 24, 2026, 00:30 IST

## One-line pitch

**HomeOps is a persistent household-maintenance assistant that remembers what you own, tracks warranties and servicing, reminds you what needs attention, and helps you contact the right service provider.**

## The problem

Household information is fragmented across receipts, warranty cards, manuals, email threads, messaging apps, calendars, and memory. When an appliance breaks, people have to reconstruct its model, purchase date, warranty status, previous repairs, and the best way to request service. Routine servicing and warranty expiry are easy to forget.

Voice assistants are convenient for asking questions, but HomeOps supplies the persistent household records and task-specific tools needed to follow through.

## The product

HomeOps is an assistant integration built around a real Model Context Protocol (MCP) server. A compatible assistant can use HomeOps tools to read and update household-maintenance records. For the hackathon, a web application simulates an Alexa+-style conversational experience and calls the same MCP server at runtime.

HomeOps has five core capabilities:

1. **Household inventory:** keep appliance/fixture name, location, brand, model, purchase date, warranty dates, manuals and receipt references.
2. **Warranty and maintenance tracking:** show approaching warranty expiry and service due dates; let users create reminders and mark work complete.
3. **Persistent service history:** record issues, troubleshooting notes, repairs, invoices/receipt references, dates and outcomes.
4. **Service discovery and handoff:** help users find a provider using a Google Maps search, prepare a WhatsApp message, email or phone action, or open a provider's supplied booking page.
5. **Actionable records:** generate a concise technician brief from stored information, including known history and explicit unknowns.

## Primary user

A person or household that owns several appliances and wants one reliable place to track their care. The initial demo uses one household and fictional seed records rather than a multi-user production account system.

## Example user journey

1. User: “Is my washing machine still under warranty?”
2. HomeOps retrieves the saved appliance record and reports the recorded warranty end date, clearly noting if purchase or warranty details have not been verified.
3. User: “Remind me a month before it expires.”
4. HomeOps stores a reminder with a due timestamp and timezone.
5. Later: “The washing machine is leaking again. Have we seen this before?”
6. HomeOps finds matching maintenance incidents and displays their recorded dates and outcomes.
7. User: “Help me find a repair service.”
8. HomeOps prepares a repair brief and offers relevant next steps: a Google Maps search, a prefilled WhatsApp message when a provider number exists, an email or phone link, an official booking page if supplied, or a simulated slot in demo mode.
9. Any actual message or booking is user-initiated unless a real, authorized provider API is implemented. HomeOps must never claim a request was sent, received, or booked just because it generated or opened a link.

## What makes HomeOps more than a chatbot?

- It keeps structured, durable records between conversations.
- It uses source-backed data instead of guessing about warranties or previous repairs.
- Its tools perform bounded actions: create a reminder, log an incident, draft a request, or generate a handoff.
- The UI shows the MCP tools invoked and the resulting records.
- It separates “prepared,” “opened by the user,” “submitted,” and “confirmed” states rather than overstating progress.

## Product modes

### 1. Demo mode

Uses fictional assets, warranties, maintenance events, providers and slots. Supports a reliable end-to-end walkthrough and reset. All seeded records and simulated bookings are labelled as demo data.

### 2. Real handoff mode

Uses user-entered household information and provider contact information. Builds external action links:

- Google Maps search URL for provider discovery.
- WhatsApp click-to-chat link with a prefilled message, when a valid phone number is present.
- `tel:` and `mailto:` links.
- A provider booking URL that the user has supplied or that is stored in a verified provider record.

These handoffs open external apps/pages; they do not themselves send a message or confirm an appointment. The user reviews and completes the action.

### 3. Future provider integrations

A real booking/marketplace integration could submit requests and read confirmations through a provider-supported, authorized API. This is not necessary for the hackathon MVP and must not be represented as implemented.

## Hackathon positioning

- **Alexa+ primary track:** deliver a self-hosted MCP server using Streamable HTTP and an Alexa+-style browser simulation that invokes it. The project is not connected to a physical Alexa device or the gated Alexa+ partner environment.
- **AWS Builder mini-challenge:** use Amazon Bedrock at runtime for a grounded maintenance/technician summary, with structured records supplied by the backend. Only claim this mini-challenge if a real Bedrock invocation succeeds, the code path is included in the repository, and the integration is documented in the submission feedback.
- **No hardware dependency:** no Alexa device, smart-home sensor or live repair marketplace is required.

## MVP scope

### Must ship

- Household asset inventory with warranty/purchase fields.
- Maintenance/incident history with recorded timestamps and sources.
- Create and list reminders, including warranty expiry and routine service.
- Find previous incidents for an asset and generate a technician brief.
- Provider handoff options: Maps search, WhatsApp draft, `tel:`, `mailto:`, and optional provider booking link.
- Simulated provider slots and a confirmation-gated demo booking.
- React-based assistant UI connected to a backend that uses an actual MCP client to call the separate MCP server.
- Visible MCP tool activity and labels for fictional data / simulated bookings.
- SQLite persistence, deterministic seed/reset, tests, README and open-source license.

### Should ship if the core is stable

- Amazon Bedrock summarization behind a provider interface, with deterministic fallback.
- Browser notification/toast while the app is open when a reminder is due; due reminders must also remain visible after restarting the app.
- Import simple appliance details from a user-selected document or manual entry, if this does not delay the core flow.

### Not required for the hackathon

- Actual Alexa+ partner onboarding or a physical Echo device.
- Real provider marketplace API, automatic WhatsApp sending, payments or dispatch.
- Background push notifications to a phone when the app/backend is not running.
- Web crawling, autofilling arbitrary provider sites, or scraping booking pages.
- Production multi-household accounts, cloud sync, IoT integration or mobile app.

## Product principles

1. **Ground truth over confidence:** show what is stored, sourced, user-entered or unknown.
2. **Confirm before consequential actions:** no actual message or booking is sent without explicit user action.
3. **Honest status:** opening a link is not a sent message; a draft is not a request; a request is not a confirmed appointment.
4. **Useful even without an LLM:** core flows must work through deterministic routing and structured tools.
5. **Privacy by default:** minimize data passed to external model services; demo with fictional records; never commit personal data or secrets.

## MVP success criteria

- A clean checkout runs on a Linux laptop with documented commands.
- An MCP client initializes, lists the HomeOps tools, and successfully calls tools over Streamable HTTP.
- The web simulator's primary workflow invokes the running MCP server via an MCP client; it does not fake tool calls or bypass MCP to query the database.
- A user can inspect a warranty, create a reminder, recall a previous repair, and prepare a real-world provider handoff.
- A simulated booking requires visible confirmation and remains clearly labelled as simulated.
- The technician brief contains only facts grounded in stored records and shows timestamps/source IDs.
- The demo video is public, in English and under three minutes.
