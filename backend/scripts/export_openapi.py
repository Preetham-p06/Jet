"""Write the OpenAPI schema to backend/openapi.json (committed; the dashboard
generates its TypeScript types from it).

    uv run python scripts/export_openapi.py          # write
    uv run python scripts/export_openapi.py --check  # exit 1 if the file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

OUTPUT = BACKEND / "openapi.json"


def render() -> str:
    # Fixed settings so the schema never depends on the local environment.
    settings = Settings(_env_file=None, database_url="sqlite://")  # type: ignore[call-arg]
    schema = create_app(settings).openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if openapi.json is stale")
    args = parser.parse_args()

    rendered = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print("openapi.json is stale; run: uv run python scripts/export_openapi.py")
            return 1
        print("openapi.json is up to date")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
