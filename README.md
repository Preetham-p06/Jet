# JetStream AI

Quote intelligence for private aviation charter brokers.

## Structure

- `frontend/` — Next.js marketing site and broker dashboard
- `backend/` — FastAPI API: quote extraction, true-cost normalization, flags, ranking and proposals

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on http://localhost:3001.

## Run the backend

```bash
cd backend
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

API docs are at http://127.0.0.1:8000/api/v1/docs. See `backend/README.md` for details.
