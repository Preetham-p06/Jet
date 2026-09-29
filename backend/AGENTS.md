# Backend conventions

Read this before changing anything under `backend/`. The approved design lives in the
design spec; this file records the rules the code relies on.

## Commands (run from `backend/`)

```bash
uv sync --all-groups
uv run ruff check . && uv run ruff format --check . && uv run mypy app
uv run alembic upgrade head && uv run alembic check
uv run pytest -q                          # -m "not integration and not e2e" for the fast set
uv run python scripts/export_openapi.py   # after any API change; commit openapi.json
```

All five must pass before you hand work back.

## Tenant scoping

- Every table except `workspaces` has `workspace_id` (the `WorkspaceScoped` mixin).
- Load rows by id with `permissions.get_owned(db, Model, id, ctx)`. It returns **404, never
  403**, for other workspaces' rows, so IDs never leak.
- Build list queries with `permissions.scoped(select(Model), ctx)`.
- `get_current_context` scopes the session (`session.info["workspace_id"]`). From then on
  `app.db` adds workspace criteria to every ORM SELECT/UPDATE/DELETE, and refuses to flush
  rows of another workspace. A new row without `workspace_id` is filled in from the session.
- Raw `text()` SQL and Core statements bypass the guard. Do not use them for tenant data.
- Code without a request (background pipeline, public proposal) must call
  `app.db.set_workspace(session, workspace_id)` before touching tenant rows.
- Storage keys are `{workspace_id}/…`. Reads pass `workspace_id=` and are checked.

## Money and time

- Money is integer **USD cents** (`*_cents`) in the database and the API. Arithmetic uses
  `Decimal` with ROUND_HALF_UP, via `services/money.py`. Never use floats for money.
- The extraction contract carries `Money(amount_minor, currency)` in the original currency;
  normalization converts it.
- Datetimes are timezone-aware UTC (`UTCDateTime` rejects naive values). The only naive
  datetimes are local wall-clock times: `trip_legs.depart_local` (with `depart_tz`) and
  `quotes.departure_local`.
- Services take `now` as a parameter so tests can pin time.

## API

- Everything is under `/api/v1`. **No trailing slashes**, and `redirect_slashes=False`: a
  redirect would leak the backend host through the Next proxy.
- Handlers are sync `def`. Errors are `{detail, code, fields?}`. Raise `app.errors`
  exceptions (`NotFound`, `Conflict`, `Unprocessable`, ...); never build error JSON by hand.
- Lists return `Page[T]` (`{items, total}`) and take `limit`/`offset` (`api/params.py`).
- Every route declares a role gate: `AnyUser`, `Reviewer` (admin, broker) or `Admin` from
  `app.deps`. Only the allowlisted public routes skip it (a test enforces this).
- CSRF: unsafe cookie-authenticated requests need `X-JetStream-Client: web`. Bearer requests
  are exempt. Login, signup, invite accept and public accept always need the header.
- Endpoints whose service is not built yet call `errors.not_implemented(...)` (501). A stub
  service raising `NotImplementedError` also maps to 501.
- Mutations write an audit entry with `services.audit.record(db, ctx, action, entity,
  before, after)` in the same transaction. Handlers commit; services flush.
- Optimistic locking: `quote_fields.version` (`version_id_col`). A stale write raises
  `StaleDataError`, which maps to 409 `stale_version`.

## Contracts are frozen

These files are shared by every package and may only change through the lead:

- `app/models/**` and `alembic/versions/**`
- `app/schemas/**`
- `app/extraction/types.py`, `app/extraction/base.py`
- `app/services/contracts.py`
- `pyproject.toml`, `uv.lock`

**Contract-change protocol:** don't edit them in a package branch. Send the lead the exact
change, the reason, and who is affected. The lead applies it, adds a migration if the schema
changed (`alembic revision --autogenerate`, then review it), re-exports `openapi.json`, and
tells the other packages. Stub modules keep their signatures: implement the bodies, and
don't rename or re-type the public functions.

## Tests

- `tests/conftest.py` gives each test a fresh SQLite file and storage directory. Fixtures:
  `client` (anonymous), `client_as(role)` (Bearer), `browser_as(role)` (cookie plus CSRF
  header), `two_workspaces` (A and B, one user per role, trip JS184 each), `db`, and
  `fake_extractor` (installed on `app.state.extractor`).
- Row factories live in `tests/factories.py`; `tests/fakes.py` has `FakeExtractor` and
  result builders.
- Markers: `integration` (several packages together) and `e2e` (demo seed oracle).
- `TEST_DATABASE_URL=postgresql+psycopg://…` runs the suite against Postgres.
