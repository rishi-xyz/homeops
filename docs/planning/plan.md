# HomeOps — Build Plan

**Planning date:** October 21, 2026  
**Hackathon deadline:** October 24, 2026, 00:30 IST  
**Target:** submit before the final hours; keep a meaningful safety buffer.  
**Strategy:** prove MCP connectivity first, build one polished HomeOps workflow, add the AWS integration only after the core submission works.

## 1. Delivery priorities

### P0 — Required for a credible Alexa+ submission

- Working self-hosted MCP server over Streamable HTTP with the required protocol version verified.
- At least one real MCP client initialization, tool listing and tool call; then several core tools.
- Web simulator's runtime calls go through an MCP client to the actual running MCP server.
- Household inventory, warranty dates, reminders, maintenance history and a technician brief.
- Provider handoff actions generated from real fields (Maps search, WhatsApp draft, phone/email, stored booking link); no false claim of sending/booking.
- Deterministic fictional demo data, source-linked UI and reset script.
- README, open-source license for public repo, tests, product feedback and an English demo video under three minutes.

### P1 — Core end-to-end product completeness

- Demo service slots and a pending-to-confirmed-demo booking flow with explicit user confirmation.
- Visible tool activity and useful empty/error states.
- Repeatable main demo path from a clean seed database.

### P2 — AWS Builder mini-challenge

- Amazon Bedrock Runtime adapter for grounded technician-summary wording.
- Real invocation from the running app, with provider indicator and documented configuration.
- Product feedback names the Bedrock service and explains its real use.

Do not select AWS Builder if the project only contains a placeholder/config flag or if no real invocation can be verified.

## 2. Scope freeze

### Build

- Next.js (React + TypeScript) frontend.
- Python + FastAPI application API and MCP client.
- Separate MCP server using official Python MCP SDK and Streamable HTTP.
- SQLite, fictional household seed data and core domain services.
- Deterministic intent router so no model/API credentials are needed for the base journey.
- Warranty and reminder lifecycle, maintenance history, provider handoff, technician brief.
- Optional Bedrock summary provider with fallback.

### Do only after P0/P1 is stable

- Bedrock integration and demo proof.
- Browser speech input/output.
- Document upload or receipt extraction.
- In-app notification toast for due reminders.

### Do not build for this deadline

- Live Alexa+ partner deployment, physical Alexa support or gated Amazon developer tooling.
- Real provider marketplace API, automatic WhatsApp sending, payment, or actual dispatch.
- Provider website scraping/automation, push notifications when server is stopped, cloud accounts, multi-tenant auth or mobile app.
- Complex AWS hosting if it risks the local demo. Bedrock Runtime use is the proposed AWS Builder path; deployment to AWS is not necessary just to demonstrate that service.

## 3. Milestones and exit gates

### Phase 0 — Repository and environment (target: 45–60 minutes)

- [ ] Create repo and folders per `architecture.md`.
- [ ] Add `.gitignore`, `.env.dev.example`, `.env.prod.example`, README starter and MIT/Apache-2.0 license.
- [ ] Install dependencies and run a tiny FastAPI health endpoint.
- [ ] Add seed/reset command and verify SQLite persistence.

**Exit gate:** clean local setup and a repeatable database reset.

### Phase 1 — MCP proof of concept (first coding milestone; target: 2–3 hours)

- [ ] Install the official MCP Python SDK.
- [ ] Implement a separate MCP server with `list_assets` and `get_asset_details`.
- [ ] Serve MCP over Streamable HTTP at `/mcp` on localhost.
- [ ] Use an actual MCP client or MCP Inspector to initialize, list tools and call `get_asset_details`.
- [ ] Verify the negotiated protocol version is 2025-11-25 or later; record the test command/result.
- [ ] Add a smoke test.

**Exit gate:** a client can call a real tool and receive seeded data. Do not move on until this works.

### Phase 2 — Domain records and tools (target: 4–6 hours)

- [ ] Implement assets/warranty metadata and maintenance history.
- [ ] Implement reminders, status calculation and completion.
- [ ] Implement technician brief data assembly.
- [ ] Implement provider handoff preparation and safe Maps/WhatsApp/phone/email/booking links.
- [ ] Implement demo slots, pending request and explicit demo confirmation.
- [ ] Add unit tests for data logic and state transitions.

**Exit gate:** all core tool calls work independently against SQLite.

### Phase 3 — API/orchestrator and simulator (target: 5–7 hours)

- [ ] Create FastAPI API routes and MCP client session manager.
- [ ] Implement an allowlisted deterministic intent router for the planned prompts.
- [ ] Make the API call MCP tools for primary assistant actions; capture real trace events.
- [ ] Build responsive UI with conversation, assets, reminders, maintenance timeline, handoff cards and activity panel.
- [ ] Show sources/record IDs and clear demo badges.
- [ ] Test the full warranty → reminder → repeated issue → technician brief/handoff journey.

**Exit gate:** a user can complete the core HomeOps flow via UI and the server logs prove MCP was used at runtime.

### Phase 4 — AWS Builder integration (target: 2–4 hours; only after Phase 3)

- [ ] Configure standard AWS credentials and a Bedrock model available to the account/region.
- [ ] Implement `BedrockSummaryProvider` using Bedrock Runtime; send only the relevant synthetic structured records.
- [ ] Keep deterministic fallback for credentials, permissions, model access or service errors.
- [ ] Run and record a real invocation through the running application.
- [ ] Verify the generated brief against record IDs; add a provider indicator and document what Bedrock does.

**Exit gate:** a real model call works end-to-end. Otherwise, keep the fallback and do not claim the AWS Builder mini-challenge.

### Phase 5 — Reliability and UX (target: 3–4 hours)

- [ ] Add no-results, missing-contact, invalid-date and external-link error cases.
- [ ] Test reminder due-state after refresh/restart.
- [ ] Confirm booking is not finalized before a user click.
- [ ] Ensure no UI message implies a real message was sent or provider accepted the job.
- [ ] Check links, encode text, validate `https` provider booking links, and preview outgoing text.
- [ ] Run tests and `git status`; verify no secrets or personal data are committed.

**Exit gate:** complete scenario runs twice after reset.

### Phase 6 — Submission package (protect this time; target: 3–4 hours)

- [ ] Finish README setup, architecture, features, demo limitations and exact run/reset commands.
- [ ] Verify the repository is public and has a clearly discoverable open-source license, or follow the hackathon's private-repository sharing instructions.
- [ ] Record a public English demo video under three minutes.
- [ ] Show the browser simulation, actual MCP tool activity and the full HomeOps workflow.
- [ ] If claiming AWS Builder, show evidence of the real Bedrock-backed step and describe the integration accurately.
- [ ] Complete product feedback for every tool/API/SDK used: purpose, what worked, what needs work, onboarding experience, and whether you would use it again.
- [ ] Fill project description, tracks and any required extra mini-challenge fields.
- [ ] Submit early enough to leave a buffer before October 24, 00:30 IST.

## 4. Suggested timeline (IST)

| Window | Target outcome |
|---|---|
| Wed Oct 21 afternoon | Repo, local setup, seed data, MCP server/client proof |
| Wed Oct 21 evening | Asset/warranty/history/reminder tools and tests |
| Thu Oct 22 morning | Provider handoff links, technician brief, demo request state machine |
| Thu Oct 22 afternoon/evening | Simulator UI + API/orchestrator calling MCP at runtime |
| Fri Oct 23 morning | End-to-end workflow, fix bugs, README and license |
| Fri Oct 23 midday/afternoon | Bedrock integration if core is stable; run real smoke test if claiming AWS Builder |
| Fri Oct 23 afternoon/evening | Record and upload video; product feedback; final regression |
| Fri Oct 23 evening | Target submission, leaving several hours before the deadline |

This timeline is a planning target, not permission to leave the submission until the last minute. Drop optional features rather than dropping the real MCP call, complete workflow, test run, or video.

## 5. Main demo script

Use one coherent story:

1. “Is my washing machine still under warranty?” Show the asset record, stored dates and source/provenance.
2. “Remind me a month before it expires.” Create and show a persisted reminder.
3. “The washing machine is leaking again. Have we seen this before?” Show the previous maintenance incident and timestamp.
4. “Prepare a brief for the technician.” Show a record-grounded brief with unknown fields identified.
5. “Help me contact a technician.” Show Maps search and a prefilled WhatsApp message (if the selected seeded provider has a number); the user explicitly opens the channel.
6. Optionally show fictional slots and a confirmation-gated demo booking, clearly labelled “no real provider contacted.”
7. Show MCP calls in the activity panel. If AWS Builder is claimed, show the Bedrock-backed summary/provider indicator.

Keep the demo to 2–2.5 minutes, leaving a buffer below the three-minute limit.

## 6. Risk and fallback table

| Risk | Fallback |
|---|---|
| MCP integration takes longer than expected | Reduce tool count but keep actual MCP initialize/list/call and one end-to-end tool-backed flow. |
| No LLM/AWS credentials | Use deterministic intent routing and deterministic summary; do not claim AWS Builder. |
| Bedrock permission/model access fails | Keep app functional; diagnose only if P0/P1 stable. |
| Real provider contact data unavailable | Use Maps search or clearly labelled fictional providers; never invent a phone number or claim live appointment availability. |
| Browser/external link cannot open | Keep the message draft visible and provide copy action. |
| UI takes too long | Keep a simple, polished simulator rather than adding voice/media features. |
| Scope creep | Drop voice, document extraction and cloud deployment before cutting MCP, reminder, history, handoff, tests or submission requirements. |
| AWS use is not truly integrated | Do not tick AWS Builder; submit a strong Alexa+ entry instead. |

## 7. Definition of done

- Core P0 and P1 checklist items are verified.
- The app can be run from documented steps on a clean checkout.
- MCP calls are real and visible in runtime traces.
- Household records and reminders persist.
- Provider handoffs make no false claims about sending or booking.
- Video and Devpost submission are complete before the deadline.
- AWS Builder is claimed only if a real Bedrock integration was exercised and documented.

## 8. Official references

- Hackathon rules: https://amazonappdev2026.devpost.com/rules
- Hackathon FAQ: https://amazonappdev2026.devpost.com/details/faqs
- Alexa+ MCP QuickStart: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart
- Official MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Amazon Bedrock overview: https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html
