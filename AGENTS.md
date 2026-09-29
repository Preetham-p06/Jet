# JetStream AI

Quote intelligence for private aviation charter brokers.

## Repo layout

- `frontend/` holds the Next.js marketing site and broker dashboard. Run all npm commands from inside `frontend/`.
- `frontend/AGENTS.md` holds the Next.js-specific rules. Read it before changing frontend code.
- `backend/` holds the Python FastAPI API (uv, SQLAlchemy, Alembic). Run all uv commands from inside `backend/`.
- `backend/AGENTS.md` holds the backend conventions: tenant scoping, money in cents, no trailing slashes, and the contract-change protocol. Read it before changing backend code.
