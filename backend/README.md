# JetStream AI backend

FastAPI service behind the broker dashboard. It extracts charter quotes from PDFs, emails and
SMS, normalizes them to a true cost, flags missing charges, ranks the quotes and publishes
client proposals.

Python 3.11+, managed with [uv](https://docs.astral.sh/uv/). SQLite by default; Postgres via
`DATABASE_URL`.

## Setup

```bash
cd backend
uv sync --all-groups              # runtime + dev tools; add --extra postgres for Postgres
cp .env.example .env              # optional; every setting has a dev default
uv run alembic upgrade head       # creates ./jetstream.db
```

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000/api/v1 (health at `/api/v1/health`)
- Interactive docs: http://127.0.0.1:8000/api/v1/docs
- OpenAPI schema: http://127.0.0.1:8000/api/v1/openapi.json

The Next.js dashboard proxies `/api/*` here (`BACKEND_URL`), so the session cookie is
first-party and CORS stays off.

For a quick token from the command line:

```bash
curl -s -X POST localhost:8000/api/v1/auth/token -d username=you@example.com -d password=...
```

## Checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app
uv run alembic upgrade head && uv run alembic check
uv run pytest -q
uv run python scripts/export_openapi.py --check   # re-export without --check after API changes
```

## Layout

| Path | What lives there |
|---|---|
| `app/main.py` | `create_app()`: routers, middleware, error handlers |
| `app/config.py` | Settings (environment and `.env`) |
| `app/db.py` | Engine, sessions, tenant guards |
| `app/deps.py`, `app/permissions.py` | Auth context, role gates, `get_owned` / `scoped` |
| `app/models/` | SQLAlchemy models (one migration per schema change in `alembic/versions/`) |
| `app/schemas/` | Pydantic request and response models (the API contract) |
| `app/extraction/` | Extraction contract, rules and Claude extractors |
| `app/services/` | Pipeline, pricing engine, review, proposals, analytics |
| `app/api/routes/` | One router per area, all under `/api/v1` |
| `tests/` | `unit/`, `integration/`, `api/`, `e2e/`, plus shared fixtures |

See `AGENTS.md` for conventions.
