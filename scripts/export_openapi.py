# scripts/export_openapi.py
"""Write the FastAPI application's OpenAPI 3.1 schema to ``docs/api/openapi.json``.

Builds ``weatherbot.web.app.create_app`` with an in-memory SQLite engine and placeholder
state so no user directory or filesystem state is touched, adds ``StreamEvent`` and every
model or type alias it references to ``components.schemas`` (which FastAPI's ``itemSchema``
leaves out of components), and writes the resulting OpenAPI document with two-space
indentation, UTF-8 encoding, and LF line endings. ``--check`` writes nothing and exits 1
when ``docs/api/openapi.json`` is missing or stale.

    uv run python scripts/export_openapi.py           # write docs/api/openapi.json
    uv run python scripts/export_openapi.py --check   # verify it is current
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Final, cast

from sqlalchemy import create_engine

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.persistence.database import Database
from weatherbot.web.app import WebState, create_app
from weatherbot.web.schemas import StreamEvent

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
OPENAPI_PATH: Final = REPOSITORY_ROOT / "docs" / "api" / "openapi.json"
REF_TEMPLATE: Final = "#/components/schemas/{model}"


def _include_stream_event_schemas(schema: dict[str, object]) -> None:
    """Add ``StreamEvent`` and its ``$defs`` to ``components.schemas``."""
    components = cast(
        "dict[str, object]",
        schema.setdefault("components", {}),
    )
    schemas = cast(
        "dict[str, object]",
        components.setdefault("schemas", {}),
    )
    event_schema = StreamEvent.model_json_schema(ref_template=REF_TEMPLATE)
    defs = cast("dict[str, object]", event_schema.pop("$defs", {}))
    for name, definition in defs.items():
        schemas.setdefault(name, definition)
    schemas["StreamEvent"] = event_schema
    components["schemas"] = dict(sorted(schemas.items()))


def openapi_schema() -> dict[str, object]:
    """Build the FastAPI application's OpenAPI 3.1 schema dictionary."""
    engine = create_engine("sqlite:///:memory:")
    try:
        paths = AppPaths(
            config_dir=REPOSITORY_ROOT / "config",
            data_dir=REPOSITORY_ROOT / "data",
        )
        database = Database(engine=engine, path=paths.database_path, revision="0006")
        state = WebState(
            database=database,
            paths=paths,
            settings=Settings(),
        )
        app = create_app(state)
        schema = app.openapi()
        _include_stream_event_schemas(schema)
        return schema
    finally:
        engine.dispose()


def render() -> str:
    """Render the OpenAPI schema as the committed file's text."""
    return json.dumps(openapi_schema(), indent=2, ensure_ascii=False) + "\n"


def is_stale(path: Path = OPENAPI_PATH) -> bool:
    """Return whether ``path`` is missing or differs from a fresh export."""
    return not path.is_file() or path.read_text(encoding="utf-8") != render()


def write(path: Path = OPENAPI_PATH) -> Path:
    """Write ``docs/api/openapi.json`` with UTF-8 encoding and LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8", newline="\n")
    return path


def main(argv: list[str] | None = None) -> int:
    """Write or check ``docs/api/openapi.json``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="verify; write nothing")
    arguments = parser.parse_args(argv)
    rel = OPENAPI_PATH.relative_to(REPOSITORY_ROOT).as_posix()
    if arguments.check:
        if is_stale():
            print(f"STALE {rel}")
            print("run: uv run python scripts/export_openapi.py")
            return 1
        print(f"OK {rel} is current")
        return 0
    written = write()
    print(f"wrote {written.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
