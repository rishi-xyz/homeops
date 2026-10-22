# HomeOps

**HomeOps** is a persistent household-maintenance assistant. It tracks appliances, warranties,
service history and reminders, then helps you prepare a technician brief or hand a request off to
a service provider.

The hackathon build ships a browser-based, Alexa+-style assistant simulation backed by a **real
self-hosted MCP server** over Streamable HTTP. The web app talks to a FastAPI orchestrator, and
the orchestrator calls the MCP server with a genuine MCP client on every primary assistant action.

> **Scope honesty**
> - This is **not** a live Alexa+ deployment and it needs **no Alexa hardware**.
> - Every household record, provider and appointment slot in the demo is **fictional demo data**.
> - Opening a Google Maps, WhatsApp, `tel:`, `mailto:` or provider booking link is a **handoff**,
>   never proof that a message was sent or that a booking was accepted.
> - Amazon Bedrock is an **optional** summary provider. It is only claimed if a real invocation
>   succeeds from the running application.

---

## Table of contents

- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Architecture](#architecture)
- [MCP tool surface](#mcp-tool-surface)
- [Demo walkthrough](#demo-walkthrough)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Testing](#testing)
- [Privacy and safety](#privacy-and-safety)
- [Known limitations](#known-limitations)
- [License](#license)

---

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.14 tested locally |
| Node.js | 20+ | 26 tested locally; only needed for the web UI |
| npm | 10+ | Only needed for the web UI |
| OS | Linux, macOS or WSL | Windows works via WSL |
| Network | PyPI + npm registry | Only for the first install |

No cloud account, no API key and no paid service is required for the core demo. The MCP server,
the API and the web app all bind to loopback.

---

## Quick start

```bash
# 1. Install (uv is optional - plain venv + pip works too)
uv venv --python 3.14                                  # or: python3 -m venv .venv
source .venv/bin/activate                              # or: source .venv/Scripts/activate
uv pip install -e ".[dev]"                             # or: pip install -e ".[dev]"

# 2. Load the fictional demo household
make seed

# 3. Install the web dependencies (only needed for the browser UI)
cd apps/web && npm install && cd ../..

# 4. Run everything (MCP server + API + web app)
make dev
```

Then open:

| Surface | URL |
|---|---|
| Web simulator | <http://127.0.0.1:5173> |
| FastAPI orchestrator | <http://127.0.0.1:8000> |
| API health check | <http://127.0.0.1:8000/health> |
| MCP server (Streamable HTTP) | <http://127.0.0.1:8001/mcp> |

Stop everything with `make stop`.

### Without `make`

```bash
# terminal 1 - MCP server
.venv/bin/python -m homeops_mcp_server.server

# terminal 2 - API / orchestrator
.venv/bin/uvicorn homeops_api.main:app --host 127.0.0.1 --port 8000

# terminal 3 - web app
cd apps/web && npm run dev
```

---

## Commands

| Command | What it does |
|---|---|
| `make install` | Create the virtualenv and install Python dependencies |
| `make install-web` | Install npm dependencies for the web app |
| `make seed` | Load the fictional demo household into the local SQLite database |
| `make reset` | Delete the local database and rebuild it from the seed (clean demo state) |
| `make status` | Print what is currently stored in the local database |
| `make api` | Start the FastAPI orchestrator on `127.0.0.1:8000` |
| `make mcp` | Start the MCP server on `127.0.0.1:8001/mcp` |
| `make web` | Start the Vite dev server on `127.0.0.1:5173` |
| `make dev` | Start all three processes together with a single stop command |
| `make stop` | Stop the processes started by `make dev` |
| `make test` | Run the Python test suite |
| `make test-web` | Run the web type check and build |
| `make lint` | Run Ruff over the Python code |
| `make clean` | Remove caches and the local database |

`make dev` writes PID files to `data/runtime/`, so `make stop` always terminates the right
processes. If you started a process manually, stop it with `Ctrl+C`.

---

## Architecture

```text
Browser (React + TypeScript + Vite)
        |  REST
        v
FastAPI orchestrator (services/api)          ---> Amazon Bedrock Runtime  [optional]
        |  MCP client: initialize / tools/list / tools/call
        v
HomeOps MCP server (services/mcp_server)     -- Streamable HTTP, /mcp
        |
        v
HomeOps core domain services (packages/homeops_core)
        |
        v
SQLite (data/local/homeops.db)  +  fictional seed (data/seed/household.json)
```

**The MCP boundary is real.** The browser never talks to the MCP server directly and the primary
assistant action always goes through an MCP client session against the running server. The UI
shows the tool name, status and record IDs returned by that call.

| Process | Default address | Purpose |
|---|---|---|
| MCP server | `http://127.0.0.1:8001/mcp` | Official MCP Python SDK (`mcp` >= 2.0), Streamable HTTP transport |
| FastAPI orchestrator | `http://127.0.0.1:8000` | Frontend API, deterministic intent router, MCP client session |
| Web simulator | `http://127.0.0.1:5173` | Alexa+-style conversation UI, asset views, handoff cards |

The MCP server and the API both depend on `homeops_core`, which owns validation, persistence and
state transitions. SQLite is the single source of truth; the API never writes to it directly on the
primary path.

---

## MCP tool surface

All tools validate their input, bound their result size and return structured data. Errors are
returned as structured results, never as stack traces.

| Tool | Purpose |
|---|---|
| `list_assets` | List/filter household assets with a derived warranty status |
| `get_asset_details` | Asset metadata, saved warranty dates, provenance, linked record IDs |
| `search_maintenance_history` | Search issues, services and repairs by asset, type, date or text |
| `log_maintenance_event` | Record an issue, inspection, service, repair or note |
| `create_reminder` | Create a warranty/maintenance reminder (validates date, timezone and references) |
| `list_reminders` | List reminders with recomputed due/overdue state |
| `complete_reminder` | Mark a reminder complete (idempotent) |
| `snooze_reminder` | Postpone a reminder to a new due time |
| `cancel_reminder` | Cancel a reminder |
| `get_technician_brief` | Record-grounded brief with source record IDs and explicit unknowns |
| `prepare_service_handoff` | Maps search, WhatsApp draft, `tel:`, `mailto:` and booking-page actions |
| `list_demo_service_slots` | Fictional appointment slots (clearly marked as demo data) |
| `draft_demo_service_request` | Create a pending simulated request - never confirms anything |
| `confirm_demo_service_request` | Confirm a pending simulated request -> `confirmed_demo` (idempotent) |

---

## Demo walkthrough

1. **"Is my washing machine still under warranty?"** - the asset record, the saved dates and the
   provenance of each field are shown. The answer states that it is *based on the saved dates*.
2. **"Remind me a month before it expires."** - a reminder is created and persisted.
3. **"The washing machine is leaking again. Have we seen this before?"** - the previous incident
   records, their timestamps and their source IDs are listed.
4. **"Prepare a brief for the technician."** - a brief assembled only from stored records, with
   unknown fields listed as unknown.
5. **"Help me contact a technician."** - a Maps search link, a prefilled WhatsApp message (only for
   a provider that has a stored number), phone, email and the provider's own booking page. The
   recipient and the full message are shown before anything is opened.
6. **Optional:** pick a fictional slot, create a simulated request and confirm it. The UI states
   that no real provider has been contacted.
7. The activity panel shows the MCP tool calls that actually ran, with names, status and record IDs.

---

## Project layout

```text
homeops/
├── apps/web/                     React + TypeScript + Vite simulator
├── services/
│   ├── api/homeops_api/          FastAPI app, routes, orchestrator, MCP client
│   └── mcp_server/               Official MCP SDK server, Streamable HTTP
├── packages/homeops_core/        Models, SQLite access, domain services, seed loader, CLI
├── data/
│   ├── seed/household.json       Fictional demo household, providers and slots
│   └── local/                    Local SQLite database (git-ignored)
├── tests/                        Unit, MCP and API tests
├── docs/                         Demo notes and diagrams
├── Makefile                      install / run / stop / seed / reset / test
└── LICENSE                       MIT
```

---

## Configuration

Every setting has a working default, so the project runs with no `.env` at all. Copy
`.env.example` to `.env` to override anything (`.env` is git-ignored).

| Variable | Default | Purpose |
|---|---|---|
| `HOMEOPS_HOME` | repository root | Base path for relative paths |
| `HOMEOPS_DB_PATH` | `data/local/homeops.db` | SQLite database location |
| `HOMEOPS_SEED_DIR` | `data/seed` | Location of the fictional seed |
| `HOMEOPS_TIMEZONE` | `Europe/London` | Household timezone for reminders and warranty maths |
| `HOMEOPS_EXPIRING_SOON_DAYS` | `30` | Threshold for the "expiring soon" warranty status |
| `HOMEOPS_DEMO_MODE` | `true` | Marks seeded records as fictional demo data |
| `HOMEOPS_MCP_URL` | `http://127.0.0.1:8001/mcp` | Where the orchestrator reaches the MCP server |
| `HOMEOPS_API_HOST` / `HOMEOPS_API_PORT` | `127.0.0.1` / `8000` | API bind address |
| `HOMEOPS_SUMMARY_PROVIDER` | `deterministic` | `deterministic` or `bedrock` |
| `AWS_REGION` / `BEDROCK_MODEL_ID` | unset | Only needed for the optional Bedrock path |

AWS credentials are **never** read from `.env` by the application and are never committed. The
optional Bedrock path uses the standard AWS credential chain (`AWS_PROFILE`, instance role, ...).

---

## Testing

```bash
make test        # pytest: domain rules, MCP smoke test, API integration test
make test-web    # TypeScript type check + production build
```

The suite covers warranty classification (active / expiring / expired / unknown), the reminder
lifecycle and timezone handling, maintenance search with and without results, handoff link
construction and message encoding, missing provider contact data, an MCP initialize/list/call smoke
test over Streamable HTTP, and the rule that a simulated request cannot be confirmed without an
explicit confirmation.

---

## Privacy and safety

- No real household data is included. The seed is fictional, labelled `is_demo` and marked with the
  `demo_seed` source type.
- `.env`, credentials, local databases, logs, receipts and user documents are git-ignored.
- All three services bind to loopback by default.
- There is no shell execution, no unrestricted SQL, no arbitrary URL fetching and no model-generated
  destination URL. Every outbound link is built from stored fields or a fixed public endpoint, and
  every parameter is URL-encoded.
- Outbound links are only opened after the user clicks, and the app records at most
  `handoff_opened` - never "sent" or "confirmed".
- Optional model calls only ever receive the minimal synthetic records that make up the brief.

---

## Known limitations

- The simulator is **not** an Alexa+ deployment. There is no Alexa device support, no Alexa+ add-on
  publication and no voice pipeline.
- Reminders are computed at query time. There is no OS-level push notification when the app is
  closed.
- Warranty status is a date comparison of the records HomeOps holds. It is not a legal or
  contractual determination - manufacturer terms, exclusions and proof of purchase decide that.
- Provider data is fictional in the demo. Real providers are not integrated, and no availability
  is verified.
- The intent router is deterministic and allowlisted. Ambiguous requests trigger a clarifying
  question rather than an invented answer.
- The local SQLite database is single-user. There is no authentication, multi-tenancy or cloud
  deployment.

---

## License

MIT - see [LICENSE](LICENSE). All demo records, providers and appointments are fictional and
fictional-only.


---

## Adding HomeOps MCP to coding agents

HomeOps exposes its tools via a Streamable HTTP MCP server at `http://127.0.0.1:8001/mcp`. You can connect any MCP-compatible coding agent to it while running the server locally.

### OpenCode (this repo)
This repo includes configuration files:
- `opencode.jsonc` - OpenCode config with the HomeOps MCP server
- `.opencode/mcp.json` - Alternative MCP configuration

To use it:
1. Start the services: `make dev` (or start MCP server separately with `make mcp`)
2. OpenCode will automatically pick up `opencode.jsonc` if present in the repo root
3. The HomeOps tools will be available for use

### Claude Code
Add to your Claude Code MCP settings (`~/.claude.json` or project settings):

```json
{
  "mcpServers": {
    "homeops": {
      "url": "http://127.0.0.1:8001/mcp",
      "type": "http"
    }
  }
}
```

### Cursor
In Cursor Settings → MCP → Add new MCP server:
- Name: `homeops`
- Type: `http` 
- URL: `http://127.0.0.1:8001/mcp`

Or add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "homeops": {
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

### Continue.dev
Add to `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "homeops",
      "type": "streamable-http",
      "url": "http://127.0.0.1:8001/mcp"
    }
  ]
}
```

### Cline / RooCode
Add to MCP settings:
```json
{
  "mcpServers": {
    "homeops": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

### Generic MCP client
Any client supporting MCP Streamable HTTP transport can connect to:
- URL: `http://127.0.0.1:8001/mcp`
- Transport: `streamable-http`
- Protocol version: `2025-11-25` or later

**Note:** The server binds to loopback only by default. Ensure `make dev` or `make mcp` is running before connecting.


---

## Web simulation with Vercel AI SDK + OpenRouter

The web UI can optionally use [Vercel AI SDK](https://ai-sdk.dev/) with [OpenRouter](https://www.openrouter.ai/) for enhanced AI capabilities in the browser simulation.

### Setup

1. Get an API key from [OpenRouter](https://www.openrouter.ai/keys)
2. Configure environment variables:

```bash
# In .env (root)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# In apps/web/.env.local
VITE_USE_OPENROUTER=true
VITE_OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

3. Install dependencies in the web app:

```bash
cd apps/web
npm install ai @ai-sdk/react @openrouter/ai-sdk-provider
```

4. Start the services as usual with `make dev`

**Note:** The core HomeOps flow always goes through the real MCP server via the FastAPI orchestrator regardless of AI provider settings. OpenRouter integration is for enhanced web simulation features only and requires your own API key.


### Using Amazon Bedrock instead of OpenRouter

Since Bedrock is already integrated, you can use it for the web simulation:

1. Install boto3: `pip install -e ".[aws]"`
2. Configure AWS credentials (via AWS CLI profile, env vars, or IAM role)
3. Set in `.env`:
```bash
HOMEOPS_SUMMARY_PROVIDER=bedrock
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
AWS_REGION=eu-west-1
```
4. Start services with `make dev` - the API will use Bedrock for brief summaries when enabled

For general chat in the web UI, the current flow goes through the deterministic MCP-backed orchestrator. You can extend it by adding a Bedrock-powered chat endpoint if needed.


---

## New: Docker & Next.js Frontend

HomeOps now supports containerized deployment with Docker Compose and a modern Next.js frontend.

### Architecture with Docker
```bash
docker compose up --build
```

Services:
- **PostgreSQL** (port 5432) - Primary database
- **Redis** (port 6379) - Caching layer  
- **MCP Server** (port 8001) - Streamable HTTP MCP server
- **FastAPI API** (port 8000) - Orchestrator with Bedrock integration
- **Next.js Web** (port 3000) - Modern landing page + demo interface

### Frontend
- **Landing Page** (`/`): Marketing page with features, tech stack, and CTA
- **Demo/MVP** (`/demo`): Interactive AI assistant powered by MCP tools and Bedrock

### Amazon Bedrock Integration
The API uses Amazon Bedrock for AI-powered technician brief summaries. Configure via environment variables:
```bash
HOMEOPS_SUMMARY_PROVIDER=bedrock
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
AWS_REGION=eu-west-1
```

Credentials are resolved via AWS credential chain (AWS CLI, IAM roles, etc.).
