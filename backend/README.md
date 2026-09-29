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

## Security notes

- **Client IP.** Rate limits and audit entries use the caller's IP. `X-Forwarded-For` is
  believed only when the direct peer is in `TRUSTED_PROXIES` (IPs or CIDRs, default
  `127.0.0.1,::1`, i.e. a Next server on the same host); the client is then the rightmost
  untrusted hop. Add your proxy's address when Next or a load balancer runs elsewhere, and
  never list addresses that the public can reach directly.
- **Login throttling.** At most `LOGIN_RATE_LIMIT` attempts per client IP per
  `LOGIN_RATE_WINDOW_S`. Per account, after `LOGIN_BACKOFF_AFTER` failed logins each
  attempt waits a short backoff (1 s, doubling, capped at `LOGIN_BACKOFF_MAX_S`). There is no
  lockout, so an attacker cannot keep the owner out. A successful login clears the backoff.
- **Logout** bumps the user's `token_version`. This revokes the token even if it was copied,
  and it also **ends the user's other sessions** (other browsers and Bearer tokens), as a
  password change does.
- **Production** (`ENV=prod`) refuses to start without a unique `SECRET_KEY` of at least 32
  characters and `COOKIE_SECURE=true`.
- **Uploads.** An ingest request whose body exceeds `MAX_UPLOAD_MB` (plus 1 MB of form
  overhead) gets 413 before it is parsed, and a body without `Content-Length` is cut off at
  the same limit. `GET /api/v1/meta/vocabulary` returns `max_upload_mb` for the dashboard.
  Emails are limited to `MAX_ATTACHMENTS` PDF attachments and `MAX_TOTAL_PAGES` pages in
  total; the rest are skipped with a warning in the processing log.
- **Stuck documents.** At startup, documents still `pending` or `processing` after
  `STALE_DOCUMENT_MINUTES` (background work lost in a restart) are marked `failed` with an
  error, so the dashboard can offer to reprocess them.

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
