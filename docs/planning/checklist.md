# HomeOps — Build, Qualification and Submission Checklist

Use this as the single source of truth. Check an item only after it has been implemented and tested. The Alexa+ track is the primary target; AWS Builder is conditional on a real Amazon Bedrock invocation.

## A. Repository and local setup

- [ ] Create the `homeops` Git repository.
- [ ] Add an open-source license (MIT or Apache-2.0) if submitting public, or follow the Devpost instructions for sharing a private repository.
- [ ] Add `.gitignore` for `.env`, credentials, local databases, logs, user documents and test output.
- [ ] Add `.env.dev.example` and `.env.prod.example` with placeholders only, no real credentials.
- [ ] Add README with system requirements, install/run/stop/reset/test commands, architecture and known limitations.
- [ ] Seed only fictional demo household, provider and appointment data.
- [ ] Add a repeatable seed/reset command.

## B. Alexa+ primary track — required if using MCP route

- [ ] MCP server is implemented with the official MCP Python SDK or compatible SDK.
- [ ] Server uses **Streamable HTTP** rather than legacy standalone HTTP+SSE.
- [ ] Actual MCP client can initialize a session, list available tools and call at least one tool.
- [ ] Verify the initialized session uses MCP specification version **2025-11-25 or later**.
- [ ] Server tool definitions have typed/validated schemas and bounded behavior.
- [ ] The app backend's primary interaction calls tools through an actual MCP client to the running MCP server.
- [ ] Browser UI does not fabricate MCP traces or bypass the server for its main assistant action.
- [ ] UI shows tool names, success/failure and the records returned.
- [ ] Record or save evidence of successful runtime tool discovery/call for debugging and demo prep.

### Alternative-route guardrail

- [ ] If the MCP route cannot be completed, the fallback is a genuine, polished Alexa+-style web simulation with source code and a working demonstrated user journey, as allowed by the hackathon rules.
- [ ] Do not claim a physical Alexa device, live Alexa+ connection, partner-tool access or Alexa+ deployment that does not exist.

## C. Core HomeOps product

- [ ] User can view household assets and appliance details.
- [ ] Warranty dates, source/provenance and unknown fields are shown clearly.
- [ ] Warranty status is described as based on saved dates unless verified from an official source.
- [ ] User can create a warranty-expiry or maintenance reminder.
- [ ] Upcoming and overdue reminders are shown correctly with timezone-aware dates.
- [ ] User can mark a reminder complete; the completed item does not reappear as due.
- [ ] User can log a maintenance issue/service/repair event.
- [ ] User can search previous maintenance history and see source IDs and timestamps.
- [ ] User can generate a technician brief from stored asset/event information.
- [ ] Missing records remain unknown; no LLM-invented purchase date, warranty, repair, provider or timestamp is shown as fact.

## D. Real-world provider handoff

- [ ] Google Maps search links are built using encoded user-selected service/locality details.
- [ ] WhatsApp message is prefilled only when a valid provider number is available.
- [ ] Message recipient and content are previewed before opening WhatsApp or another external channel.
- [ ] `tel:` / `mailto:` links are available only when real contact data is stored.
- [ ] Provider booking page is opened only from a known, validated stored URL (prefer HTTPS).
- [ ] No automatic WhatsApp/email sending is claimed or performed.
- [ ] Link open is recorded, at most, as `handoff_opened`; never as message sent or appointment confirmed.
- [ ] When there are no contact details, app offers a Maps search or says details are unavailable without inventing contacts.
- [ ] User can still copy the prepared technician brief/message if the external app fails to open.

## E. Demo booking state machine

- [ ] Fictional service providers and slots are labelled demo data.
- [ ] User can draft a request without confirming it.
- [ ] UI displays provider, slot, issue summary and explicit “simulated booking” notice.
- [ ] Only an explicit user confirmation changes status to `confirmed_demo`.
- [ ] Duplicate confirmation is idempotent.
- [ ] UI says no real service provider has been contacted.
- [ ] The demo never conflates a simulated slot with verified real availability.

## F. AWS Builder mini-challenge — only claim if every item passes

- [ ] Amazon Bedrock Runtime is called by the running HomeOps application, not just mentioned in the README.
- [ ] Model ID and AWS region are configured through environment/profile configuration, with no secrets committed.
- [ ] A real Bedrock invocation succeeds with the current account/region permissions.
- [ ] The request contains only the minimal relevant synthetic demo records.
- [ ] Model-generated summary is checked against source records; deterministic fallback works on API/permission/timeout errors.
- [ ] UI or logs show when Bedrock was used versus deterministic fallback.
- [ ] README and Devpost feedback state exactly what Bedrock does and what worked/needs improvement.
- [ ] Demo/video includes the Bedrock-backed operation if claiming AWS Builder.
- [ ] If any of these are not true, do **not** claim the AWS Builder mini-challenge.

## G. Privacy, safety and quality

- [ ] No `.env`, AWS credentials, real user phone/address, receipts or private household documents are committed.
- [ ] Local services bind to loopback unless protected authentication is intentionally configured.
- [ ] No arbitrary shell execution, unrestricted SQL, URL fetching or model-generated destination URLs.
- [ ] Inputs, IDs, limits, timestamps, timezone and state transitions are validated.
- [ ] Bedrock fallback and no-credentials startup are tested.
- [ ] UI has loading, empty, error and success states.
- [ ] All seed records and demo requests are visibly labeled.
- [ ] Full core demo works twice after reset.
- [ ] Project runs from a clean checkout using README instructions.

## H. Tests

- [ ] Warranty status: active / expiring / expired / unknown.
- [ ] Reminder create/list/due/complete/snooze and timezone handling.
- [ ] Maintenance-history search with results and no results.
- [ ] Handoff link generation and message encoding.
- [ ] Missing or invalid provider contact values are handled correctly.
- [ ] MCP initialize / list / call smoke test over Streamable HTTP.
- [ ] Test verifies the app actually calls MCP at runtime.
- [ ] Technician brief facts and timestamps match the database.
- [ ] Simulated request cannot be confirmed before explicit user confirmation.
- [ ] Bedrock mocked-client test and, if AWS Builder is claimed, a real invocation smoke test.

## I. Demo video and Devpost submission

- [ ] Public English demo video uploaded to YouTube or Vimeo.
- [ ] Video is under three minutes; target 2–2.5 minutes.
- [ ] Video shows the actual running UI, visible tool activity and a coherent workflow.
- [ ] Show warranty lookup, reminder creation, previous incident, technician brief and provider handoff.
- [ ] Show demo booking only if useful, and clearly state it is simulated.
- [ ] Show the real Bedrock operation if claiming AWS Builder.
- [ ] Public GitHub repository has a visible license, or private repository is shared with all required reviewers according to the rules.
- [ ] Submission description explains what HomeOps does and how it works.
- [ ] Select the Alexa+ track.
- [ ] Select AWS Builder only if its runtime integration is real and verified.
- [ ] Complete product feedback for every tool/API/SDK actually used: purpose, what worked, what needs work, onboarding and whether you would build with it again.
- [ ] Verify any additional mini-challenge fields before submitting.
- [ ] Submit with a buffer before the deadline: October 24, 2026, 00:30 IST.

## J. Final release gate

- [ ] `git status` checked; no secrets or accidental private data.
- [ ] All tests rerun from a clean state.
- [ ] MCP transport and protocol version verified one final time.
- [ ] Full demo rehearsed and under 2.5 minutes.
- [ ] Video, GitHub link, license and Devpost fields checked.
- [ ] Final submission saved/submitted successfully.
