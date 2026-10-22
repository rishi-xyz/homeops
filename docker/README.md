# HomeOps Docker Setup

Run the entire HomeOps stack with Docker Compose.

## Prerequisites
- Docker and Docker Compose installed
- AWS credentials configured (for Bedrock) or set in `.env`

## Quick Start

1. Copy environment file:
```bash
cp .env.example .env
```

2. Configure Bedrock (recommended):
```bash
# Edit .env
AWS_REGION=eu-west-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
HOMEOPS_SUMMARY_PROVIDER=bedrock
# AWS credentials via AWS CLI, env vars, or IAM role
```

3. Start all services:
```bash
docker compose up --build
```

4. Access the application:
- Landing Page: http://localhost:3000
- Demo/MVP: http://localhost:3000/demo
- API: http://localhost:8000
- MCP Server: http://localhost:8001/mcp
- PostgreSQL: localhost:5432

## Services
- **postgres**: PostgreSQL 16 database
- **redis**: Redis for caching/sessions
- **mcp**: HomeOps MCP server (Streamable HTTP)
- **api**: FastAPI orchestrator with Bedrock integration
- **web**: Next.js frontend (landing + demo)

## Stopping
```bash
docker compose down
```

## Rebuilding
```bash
docker compose up --build --force-recreate
```
