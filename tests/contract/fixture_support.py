# tests/contract/fixture_support.py
"""Readers shared by the contract tests over the recorded fixtures and the data-source register.

Nothing here asserts; the tests do. The recorded tree is
``tests/fixtures/recorded/<source-id>/<yyyy-mm-dd>/`` with one ``manifest.json`` per capture
directory (``scripts/record_fixtures.py`` writes it; its module docstring is the schema).
"""

import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RECORDED_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "recorded"
REGISTER_PATH = REPOSITORY_ROOT / "docs" / "DATA_SOURCES.md"
MANIFEST_NAME = "manifest.json"
DATE_NAME = re.compile(r"\d{4}-\d{2}-\d{2}")
LIVE_ORIGIN = "live"

# Layer geometries the register's tables name; the rest of a layer's rows are groups,
# mosaics, and rasters, which are drawn or counted, never queried for features.
FEATURE_GEOMETRIES = frozenset({"point", "polyline", "polygon"})
CATALOG_GEOMETRY = {
    "esriGeometryPoint": "point",
    "esriGeometryPolyline": "polyline",
    "esriGeometryPolygon": "polygon",
}
CATALOG_KINDS = {"Group Layer": "group", "Mosaic Layer": "mosaic", "Raster Layer": "raster"}


def as_object(value: object) -> dict[str, object]:
    """Return ``value`` as a JSON object, failing the test if it is not one.

    Args:
        value: A parsed JSON value.

    Returns:
        The object.
    """
    assert isinstance(value, dict), "expected a JSON object"
    return cast("dict[str, object]", value)


def as_list(value: object) -> list[object]:
    """Return ``value`` as a JSON array, failing the test if it is not one.

    Args:
        value: A parsed JSON value.

    Returns:
        The array.
    """
    assert isinstance(value, list), "expected a JSON array"
    return cast("list[object]", value)


@dataclass(frozen=True)
class CaptureDirectory:
    """One ``<source-id>/<yyyy-mm-dd>/`` directory and its parsed manifest."""

    source: str
    day: str
    path: Path
    manifest: dict[str, object]

    @property
    def label(self) -> str:
        """The directory as ``<source-id>/<yyyy-mm-dd>``, for test ids and messages."""
        return f"{self.source}/{self.day}"

    @property
    def entries(self) -> list[dict[str, object]]:
        """The manifest's ``captures``."""
        return [as_object(entry) for entry in as_list(self.manifest.get("captures"))]

    def file_names(self) -> set[str]:
        """The stored file names the manifest lists."""
        return {str(entry["file"]) for entry in self.entries}

    def payload(self, entry: dict[str, object]) -> bytes:
        """Read a capture's payload as received (decompressed when stored as gzip).

        Args:
            entry: A manifest entry.

        Returns:
            The payload bytes.
        """
        stored = (self.path / str(entry["file"])).read_bytes()
        return gzip.decompress(stored) if entry.get("stored_as") == "gzip" else stored

    def is_live(self) -> bool:
        """Whether every capture was fetched live (not harvested)."""
        return all(entry.get("origin") == LIVE_ORIGIN for entry in self.entries)


def capture_directories() -> list[CaptureDirectory]:
    """Find every capture directory under the recorded tree that has a readable manifest.

    Returns:
        The directories sorted by source and date; empty when the tree does not exist.
    """
    found: list[CaptureDirectory] = []
    if not RECORDED_ROOT.is_dir():
        return found
    for source in sorted(path for path in RECORDED_ROOT.iterdir() if path.is_dir()):
        for day in sorted(path for path in source.iterdir() if path.is_dir()):
            manifest_path = day / MANIFEST_NAME
            if manifest_path.is_file():
                manifest = as_object(json.loads(manifest_path.read_text(encoding="utf-8")))
                found.append(CaptureDirectory(source.name, day.name, day, manifest))
    return found


def latest_live(source: str) -> CaptureDirectory | None:
    """Find the newest capture directory of a source whose captures were all fetched live.

    Args:
        source: A register id.

    Returns:
        The directory, or None when the source has no live capture.
    """
    live = [item for item in capture_directories() if item.source == source and item.is_live()]
    return live[-1] if live else None


@dataclass(frozen=True)
class RegisterRow:
    """One row of the register table."""

    source_id: str
    endpoint: str
    fixture: str

    @property
    def required(self) -> bool:
        """Whether the recorder must capture this source."""
        return self.fixture == "required"


@dataclass(frozen=True)
class RegisterLayer:
    """One row of a service's layer table: the cells as the register writes them."""

    name: str
    geometry: str
    notes: str
    present: str = ""
    used: str = ""


def _cells(line: str) -> list[str]:
    # The register writes no `|` inside a cell, so a split is exact.
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _unquote(cell: str) -> str:
    return cell.strip("`")


def register_text() -> str:
    """Read the register.

    Returns:
        The text of ``docs/DATA_SOURCES.md``.
    """
    return REGISTER_PATH.read_text(encoding="utf-8")


def _section(text: str, heading: str, level: int) -> str:
    marker = f"{'#' * level} {heading}\n"
    start = text.index(marker) + len(marker)
    following = re.search(rf"^#{{1,{level}}} ", text[start:], re.MULTILINE)
    return text[start : start + following.start()] if following else text[start:]


def register_rows() -> list[RegisterRow]:
    """Parse the register table (the section "Register").

    Returns:
        One row per source id, in the register's order.
    """
    rows: list[RegisterRow] = []
    for line in _section(register_text(), "Register", 2).splitlines():
        if line.startswith("| `"):
            cells = _cells(line)
            rows.append(RegisterRow(_unquote(cells[0]), _unquote(cells[2]), _unquote(cells[4])))
    return rows


def register_layers(service: str) -> list[RegisterLayer]:
    """Parse a service's layer table (the section "### `tropical/<service>`").

    Args:
        service: The service folder name, such as ``NHC_tropical_weather``.

    Returns:
        One row per layer, in the register's order.
    """
    section = _section(register_text(), f"`tropical/{service}`", 3)
    layers: list[RegisterLayer] = []
    for line in section.splitlines():
        if line.startswith("| `"):
            cells = _cells(line)
            layers.append(RegisterLayer(_unquote(cells[0]), cells[1], cells[4], cells[2], cells[3]))
    return layers


SLOT_SERVICE = "NHC_tropical_weather"
_QUOTED = re.compile(r"`([^`]+)`")
BULLET = "\n- "


def _names(cell: str, layer: str, column: str) -> frozenset[str]:
    """Read a fields cell: quoted names, ``—``, or a reference to another table's row.

    ``as in `NHC_tropical_weather``` names the same layer in that service; ``as `{slot}
    Forecast Points``` names that row of the slot service, and ``plus `idp_subset```
    adds names to the reference.
    """
    if cell in {"—", ""}:
        return frozenset()
    quoted = _QUOTED.findall(cell)
    if cell.startswith("as in `"):
        return layer_fields(quoted[0])[layer][column] | frozenset(quoted[1:])
    if cell.startswith("as `"):
        return layer_fields(SLOT_SERVICE)[quoted[0]][column] | frozenset(quoted[1:])
    return frozenset(quoted)


def layer_fields(service: str) -> dict[str, dict[str, frozenset[str]]]:
    """Read a service's "Fields present" and "Fields v2 uses" columns, references resolved.

    Args:
        service: The service folder name, such as ``NHC_tropical_weather_summary``.

    Returns:
        By layer name: ``{"present": ..., "used": ...}``.
    """
    return {
        layer.name: {
            "present": _names(layer.present, layer.name, "present"),
            "used": _names(layer.used, layer.name, "used"),
        }
        for layer in register_layers(service)
    }


def register_section_fields(heading: str, label: str = "Fields v2 uses") -> frozenset[str]:
    """Read a section's "Fields v2 uses" bullet: the names it quotes, up to the next bullet.

    Args:
        heading: The ``##`` section, such as ``Text products``.
        label: The bullet's bold label, such as ``List fields v2 uses``.

    Returns:
        The field names, nested members as ``object.member``.
    """
    section = _section(register_text(), heading, 2)
    start = section.index(f"- **{label}:**")
    end = section.find(BULLET, start + 1)
    return frozenset(_QUOTED.findall(section[start : end if end != -1 else None]))


def register_roster_fields() -> frozenset[str]:
    """Read the roster's "Fields v2 uses" (section "NHC current storms").

    Returns:
        The field names, product members as ``object.member``.
    """
    return register_section_fields("NHC current storms")


def register_user_agent() -> str:
    """Read the User-Agent the register fixes (the code block under "User-Agent").

    Returns:
        The User-Agent string.
    """
    block = re.search(
        r"```text\n(weatherbot/[^\n]+)\n```", _section(register_text(), "User-Agent", 2)
    )
    assert block is not None, "the register's User-Agent block is missing"
    return block[1]
