# HomeOps Docker setup

Run the HomeOps stack with Docker Compose.

## Prerequisites

- Docker and Docker Compose
- AWS credentials configured through the standard chain (optional, only for Bedrock summaries)

## Quick start

1. Create the production environment file (git-ignored):

```bash
make env ENV_NAME=prod
# or: cp .env.prod.example .env.prod
```

2. Configure Bedrock if you want real summaries (optional):

```bash
# .env.prod
HOMEOPS_SUMMARY_PROVIDER=bedrock
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
AWS_REGION=eu-west-1
# Credentials come from the AWS CLI profile, environment variables or an IAM role.
```

3. Start the stack:

```bash
docker compose --env-file .env.prod up --build
```

`--env-file` is needed both for the Compose `${...}` interpolation and for the
`NEXT_PUBLIC_API_BASE_URL` build argument.

4. Open:

- Landing page: http://localhost:3000
- Demo: http://localhost:3000/demo
- API: http://localhost:8000
- MCP server: http://localhost:8001/mcp

## Services

| Service | Port | Notes |
|---|---|---|
| `mcp` | 8001 | HomeOps MCP server (Streamable HTTP) |
| `api` | 8000 | FastAPI orchestrator with optional Bedrock summaries |
| `web` | 3000 | Next.js landing page and demo |
| `postgres` | 5432 | Optional `infra` profile; reserved, app uses SQLite |
| `redis` | 6379 | Optional `infra` profile; not read by the app yet |

The application stores data in SQLite under `./data`. Postgres and Redis are
grouped behind the `infra` profile so the default stack stays small:

```bash
docker compose --env-file .env.prod --profile infra up --build
```

## Stopping

```bash
docker compose --env-file .env.prod down
```

## Rebuilding

```bash
docker compose --env-file .env.prod up --build --force-recreate
```
