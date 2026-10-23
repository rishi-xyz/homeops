# HomeOps website

Next.js app for the HomeOps website. It serves the marketing landing page (`/`) and the
assistant demo (`/demo`), which talks to the FastAPI orchestrator over REST.

## Development

```bash
npm install
npm run dev        # http://127.0.0.1:3000
```

The API base URL defaults to `http://127.0.0.1:8000`. To override it, create `.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Start the backend from the repository root with `make dev` (or `make api` for the API only).

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Start the Next.js dev server |
| `npm run build` | Production build (also type-checks) |
| `npm run start` | Serve the production build |
| `npm run lint` | Run ESLint |
