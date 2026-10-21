# scripts/export_schemas.py
"""Write the JSON Schema of every ``--json`` document to ``docs/schema/``.

Each command's document is a Pydantic model in ``weatherbot.cli.documents``; this script
renders each model's schema (JSON Schema 2020-12, with ``$schema`` and ``$id``) to
``docs/schema/<name>.schema.json``. Run it after changing a document model, and commit the
result: a test fails while a committed schema differs from a fresh export. ``--check``
writes nothing and exits 1 when a committed file is stale.

    uv run python scripts/export_schemas.py           # write every schema
    uv run python scripts/export_schemas.py --check   # verify them
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from weatherbot.cli.documents import DOCUMENTS, json_schema

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
SCHEMA_DIRECTORY: Final = REPOSITORY_ROOT / "docs" / "schema"


def render(name: str) -> str:
    """Render one document's schema as the committed file's text.

    Args:
        name: A document name, such as ``storms``.

    Returns:
        The JSON text, two-space indented, ending in a newline.
    """
    return json.dumps(json_schema(name), indent=2, ensure_ascii=False) + "\n"


def schema_path(name: str, directory: Path = SCHEMA_DIRECTORY) -> Path:
    """Return where a document's schema is committed.

    Args:
        name: A document name.
        directory: The schema directory.

    Returns:
        The path.
    """
    return directory / f"{name}.schema.json"


def stale(directory: Path = SCHEMA_DIRECTORY) -> list[str]:
    """List the documents whose committed schema differs from a fresh export.

    Args:
        directory: The schema directory.

    Returns:
        The names, in ``DOCUMENTS`` order.
    """
    names: list[str] = []
    for name in DOCUMENTS:
        path = schema_path(name, directory)
        if not path.is_file() or path.read_text(encoding="utf-8") != render(name):
            names.append(name)
    return names


def write(directory: Path = SCHEMA_DIRECTORY) -> list[Path]:
    """Write every document's schema.

    Args:
        directory: The schema directory, created if missing.

    Returns:
        The files written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in DOCUMENTS:
        path = schema_path(name, directory)
        path.write_text(render(name), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    """Write or check the schemas.

    Args:
        argv: The arguments; ``sys.argv[1:]`` when omitted.

    Returns:
        0 when written or current, 1 when ``--check`` finds a stale schema.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="verify; write nothing")
    arguments = parser.parse_args(argv)
    if arguments.check:
        names = stale()
        for name in names:
            print(f"STALE {schema_path(name).relative_to(REPOSITORY_ROOT).as_posix()}")
        if names:
            print("run: uv run python scripts/export_schemas.py")
            return 1
        print(f"OK {len(DOCUMENTS)} schemas are current")
        return 0
    for path in write():
        print(f"wrote {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
