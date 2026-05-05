# Personal Finance OS — Dashboard

React 19 + TypeScript + Vite frontend for the Personal Finance OS.

See the [root README](../README.md) for full setup instructions, feature documentation, and API reference.

## Development

```bash
# From the repo root:
make dev-dashboard        # starts Vite dev server on port 3000

# Or from this directory:
npm run dev               # dev server
npm run build             # production build (runs tsc first)
npm run lint              # ESLint
```

The dashboard expects the FastAPI server to be running on `http://localhost:8000` (configurable via `VITE_API_URL` in `dashboard/.env`).
