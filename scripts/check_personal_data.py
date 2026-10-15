# scripts/check_personal_data.py
r"""Personal-data check: the fourth check of the security gate.

Weatherbot is a public repository, so a coordinate or another personal value that
reaches a commit is published permanently. This checker blocks one before it lands. The
pre-commit hook runs it on staged files, CI runs it over every tracked file, and anyone
can run it by hand. It uses the standard library only.

Rules:
    R1  Denylist (local only): any entry of the operator's denylist, case-insensitive,
        anywhere in a scanned file, fixtures and binaries included (the bytes are
        scanned, and a gzip file is scanned again decompressed). Standalone decimal
        coordinate entries match whole numeric values, including zero padding, rather
        than prefixes of different numbers; strings and coordinate pairs remain literal.
    R2  Coordinates: a decimal latitude/longitude pair (either order, comma or space
        separated, in range, at least three decimals each) or a lat, lon, lng, latitude,
        or longitude assignment with at least three decimals, in a text file outside
        the NOAA payload trees ``tests/fixtures/recorded/`` and
        ``tests/fixtures/replay/``.
    R3  Request coordinates: every coordinate in a fixture manifest's ``url`` (an NWS
        ``/points/`` path, a ``point`` parameter, or ``lat`` and ``lon`` parameters).
    R4  Environment files: no ``.env``, ``*.env``, or ``.env.*`` file.

A coordinate passes R2 and R3 only when it equals a landmark in
``scripts/public_landmarks.toml`` to three decimals: within half a unit of the third
decimal, so either rounding of a tie passes.

Output names ``path:line`` and the rule id, never the matched text, so no terminal, CI
log, or transcript carries a personal value. Line 0 means the file name itself, and a
part of a file name that holds a personal value is printed as ``<redacted>``.

The denylist is a text file with one value per line, kept outside the repository so
that every worktree shares it and no commit can carry it: ``WEATHERBOT_DENYLIST`` if set,
else ``%APPDATA%\weatherbot\personal-denylist.txt`` on Windows and
``${XDG_CONFIG_HOME:-~/.config}/weatherbot/personal-denylist.txt`` elsewhere. Without
``--ci``, a missing or empty denylist fails closed.

Usage (from the repository root)::

    uv run python scripts/check_personal_data.py --all            # every tracked file
    uv run python scripts/check_personal_data.py FILE...          # the named files
    uv run python scripts/check_personal_data.py --self-test      # prove the rules fire
    uv run python scripts/check_personal_data.py --init-from-env .env
    uv run python scripts/check_personal_data.py --add            # one value from stdin

``--ci`` skips R1 and is set only in CI, which has no denylist. Exit status: 0 clean,
1 findings or a failed self-test, 2 a setup error.
"""

import argparse
import getpass
import gzip
import io
import json
import os
import random
import re
import shutil
import subprocess  # runs `git ls-files` from an argument list, never a shell  # nosec B404
import sys
import tempfile
import tomllib
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import zip_longest
from pathlib import Path
from typing import Self, TextIO, cast
from urllib.parse import parse_qs, unquote, urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LANDMARKS_PATH = Path(__file__).resolve().with_name("public_landmarks.toml")

DENYLIST_VARIABLE = "WEATHERBOT_DENYLIST"
DENYLIST_DIRECTORY = "weatherbot"
DENYLIST_FILENAME = "personal-denylist.txt"
DENYLIST_HEADER = (
    "# weatherbot personal-data denylist: one value per line; lines starting with # are\n"
    "# comments. It lives outside the repository on purpose: never commit, paste, or\n"
    "# share it. scripts/check_personal_data.py reads it and never prints a value.\n"
)
DENYLIST_PLACES = range(2, 7)
DENYLIST_SEPARATORS = (",", ", ", " ")
# A shorter value would match nearly every file and make the check useless.
MIN_ENTRY_LENGTH = 4

PAYLOAD_TREES = ("tests/fixtures/recorded/", "tests/fixtures/replay/")
FIXTURE_TREE = "tests/fixtures/"
MANIFEST_NAME = "manifest.json"
MANIFEST_SUFFIX = "-manifest.json"

MAX_LATITUDE = Decimal(90)
MAX_LONGITUDE = Decimal(180)
# "Equal to three decimals": within half a unit of the third decimal (about 55 m).
LANDMARK_TOLERANCE = Decimal("0.0005")

# Git's own heuristic: a NUL byte in the first 8000 bytes marks a file as binary.
BINARY_SNIFF_BYTES = 8000
GZIP_MAGIC = b"\x1f\x8b"
MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024

SYNTHETIC_SEED = 0
SYNTHETIC_ATTEMPTS = 1000
SYNTHETIC_CLEARANCE_DEGREES = 5.0
SYNTHETIC_LATITUDE_RANGE = (-60.0, 60.0)
SYNTHETIC_LONGITUDE_RANGE = (-175.0, 175.0)

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_SETUP = 2

REDACTED = "<redacted>"

OSM_OBJECT_URL = re.compile(r"https://www\.openstreetmap\.org/(?:node|way|relation)/[0-9]+")

# A number in degrees with at least three decimals. It may not continue a longer number
# (a digit, a dot, or a minus sign before it; a digit, or a dot and a digit, after it), so
# a version string never matches, while a sentence's closing period or a file extension
# does not hide a coordinate.
_DEGREES = r"-?[0-9]{1,3}\.[0-9]{3,}"
_BEFORE = r"(?<![\w.-])"
_AFTER = r"(?!\w|\.[0-9])"
COORDINATE_PAIR = re.compile(
    rf"{_BEFORE}(?P<first>{_DEGREES})(?:\s*,\s*|\s+)(?P<second>{_DEGREES}){_AFTER}"
)
COORDINATE_ASSIGNMENT = re.compile(
    r"(?P<key>(?<![A-Za-z])(?i:latitude|longitude|lat|lng|lon)"
    r"|(?<=[a-z0-9])(?:Latitude|Longitude|Lat|Lng|Lon))"
    r"[\"']?\s*(?:=>|[:=]{1,2})\s*[\"']?"
    rf"(?P<value>{_DEGREES}){_AFTER}"
)
URL_FIELD = re.compile(r'"url"\s*:\s*(?P<literal>"(?:[^"\\]|\\.)*")')
POINTS_PATH = re.compile(r"/points/(?P<lat>[^/,]+),(?P<lon>[^/]+)")

SETUP_INSTRUCTIONS = f"""\
The personal-data denylist is missing or empty, so the check cannot run: it fails closed.
Create it from the dotenv file that holds HOME_LAT and HOME_LON (it prints a count only):
    uv run python scripts/check_personal_data.py --init-from-env .env
or add one value at a time, read from standard input and never echoed:
    uv run python scripts/check_personal_data.py --add
The denylist lives outside the repository: the path in {DENYLIST_VARIABLE} if set, else
%APPDATA%\\{DENYLIST_DIRECTORY}\\{DENYLIST_FILENAME} on Windows and
${{XDG_CONFIG_HOME:-~/.config}}/{DENYLIST_DIRECTORY}/{DENYLIST_FILENAME} elsewhere."""


class SetupError(Exception):
    """A problem that stops the check before it can scan; exit status 2.

    Messages never carry a scanned or denylisted value.
    """


@dataclass(frozen=True, order=True)
class Finding:
    """One rule violation, located by file and line and never by the matched text."""

    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        """Return the ``path:line: RULE message`` form the checker prints."""
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


@dataclass(frozen=True)
class Landmark:
    """A public place whose coordinates any file, request, or example may use."""

    key: str
    name: str
    lat: Decimal
    lon: Decimal
    source: str


def _agrees(value: Decimal, landmark: Decimal) -> bool:
    return abs(value - landmark) <= LANDMARK_TOLERANCE


def _decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


@dataclass(frozen=True)
class Allowlist:
    """The landmark coordinates that R2 and R3 accept."""

    pairs: tuple[tuple[Decimal, Decimal], ...]

    @classmethod
    def from_landmarks(cls, landmarks: Iterable[Landmark]) -> Self:
        """Build the allowlist from landmarks.

        Args:
            landmarks: The public landmarks.

        Returns:
            The allowlist.
        """
        return cls(pairs=tuple((item.lat, item.lon) for item in landmarks))

    def allows_pair(self, lat: Decimal, lon: Decimal) -> bool:
        """Return whether ``(lat, lon)`` equals a landmark to three decimals.

        Args:
            lat: The latitude.
            lon: The longitude.

        Returns:
            True for a landmark.
        """
        return any(_agrees(lat, known[0]) and _agrees(lon, known[1]) for known in self.pairs)

    def allows_value(self, value: Decimal, *, latitude: bool) -> bool:
        """Return whether one coordinate equals a landmark's to three decimals.

        Args:
            value: The latitude or longitude.
            latitude: Whether ``value`` is a latitude rather than a longitude.

        Returns:
            True when some landmark has that coordinate.
        """
        axis = 0 if latitude else 1
        return any(_agrees(value, known[axis]) for known in self.pairs)


def _table(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        message = f"{what} must be a TOML table"
        raise SetupError(message)
    return cast("dict[str, object]", value)


def _landmark_degrees(value: object, limit: Decimal, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        message = f"{where} must be a number"
        raise SetupError(message)
    degrees = Decimal(str(value))
    if not degrees.is_finite() or abs(degrees) > limit:
        message = f"{where} is out of range"
        raise SetupError(message)
    return degrees


def _landmark(key: str, value: object) -> Landmark:
    entry = _table(value, f"landmark {key}")
    name = entry.get("name")
    source = entry.get("source")
    if not isinstance(name, str) or not name.strip():
        message = f"landmark {key} needs a name"
        raise SetupError(message)
    if not isinstance(source, str) or not OSM_OBJECT_URL.fullmatch(source):
        message = f"landmark {key} needs a source: an OpenStreetMap object URL"
        raise SetupError(message)
    return Landmark(
        key=key,
        name=name,
        lat=_landmark_degrees(entry.get("lat"), MAX_LATITUDE, f"landmark {key} lat"),
        lon=_landmark_degrees(entry.get("lon"), MAX_LONGITUDE, f"landmark {key} lon"),
        source=source,
    )


def load_landmarks(path: Path = LANDMARKS_PATH) -> tuple[Landmark, ...]:
    """Read and validate the public-landmark allowlist.

    Args:
        path: The landmarks TOML file.

    Returns:
        The landmarks, in file order.

    Raises:
        SetupError: The file is missing, malformed, or empty.
    """
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        message = f"cannot read the landmark allowlist {path.name}"
        raise SetupError(message) from error
    table = _table(document.get("landmarks"), "[landmarks]")
    if not table:
        message = f"{path.name} lists no landmarks"
        raise SetupError(message)
    return tuple(_landmark(key, value) for key, value in table.items())


def resolve_denylist_path(environ: Mapping[str, str], *, windows: bool, home: Path) -> Path:
    """Return where the denylist lives: the override, else the user configuration directory.

    Args:
        environ: The environment variables.
        windows: Whether the platform is Windows.
        home: The user's home directory.

    Returns:
        The denylist path.
    """
    override = environ.get(DENYLIST_VARIABLE, "").strip()
    if override:
        return Path(override).expanduser()
    if windows:
        appdata = environ.get("APPDATA", "").strip()
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
    else:
        xdg = environ.get("XDG_CONFIG_HOME", "").strip()
        base = Path(xdg) if xdg else home / ".config"
    return base / DENYLIST_DIRECTORY / DENYLIST_FILENAME


def denylist_path() -> Path:
    """Return this machine's denylist path, refusing one inside the repository.

    Returns:
        The denylist path.

    Raises:
        SetupError: The path is inside the repository.
    """
    path = resolve_denylist_path(os.environ, windows=os.name == "nt", home=Path.home())
    if path.resolve().is_relative_to(REPOSITORY_ROOT):
        message = (
            "the denylist must live outside the repository, where no commit can carry it; "
            f"point {DENYLIST_VARIABLE} elsewhere or unset it"
        )
        raise SetupError(message)
    return path


def read_denylist(path: Path) -> list[str]:
    """Read the denylist's entries, skipping blank lines and ``#`` comments.

    Args:
        path: The denylist file.

    Returns:
        The entries, or an empty list when the file does not exist.

    Raises:
        SetupError: The file exists but cannot be read.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as error:
        message = "cannot read the personal-data denylist"
        raise SetupError(message) from error
    return [line.strip() for line in text.splitlines() if line.strip() and line.strip()[0] != "#"]


def _write_denylist(path: Path, entries: Sequence[str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = path.with_name(f"{path.name}.tmp")
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(DENYLIST_HEADER)
        stream.writelines(f"{entry}\n" for entry in entries)
    staging.replace(path)


def add_entries(path: Path, entries: Iterable[str]) -> tuple[int, int]:
    """Append entries the denylist does not already hold (compared case-insensitively).

    Args:
        path: The denylist file, created with its directory when missing.
        entries: The values to add.

    Returns:
        The number of entries added, and the number the denylist now holds.
    """
    current = read_denylist(path)
    known = {entry.lower() for entry in current}
    added: list[str] = []
    for entry in entries:
        if entry.lower() not in known:
            known.add(entry.lower())
            added.append(entry)
    if added:
        _write_denylist(path, [*current, *added])
    return len(added), len(current) + len(added)


def read_dotenv(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines from a dotenv file.

    Handles ``export``, quoted values, comments, and inline comments after unquoted
    values. Never logs a value.

    Args:
        path: The dotenv file.

    Returns:
        The variables it defines.

    Raises:
        SetupError: The file cannot be read.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        message = f"cannot read the dotenv file {path.name}"
        raise SetupError(message) from error
    variables: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        line = line.removeprefix("export ").lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip() or key.lstrip().startswith("#"):
            continue
        value = value.strip()
        quoted = len(value) > 1 and value[0] == value[-1] and value[0] in "\"'"
        value = value[1:-1] if quoted else value.split(" #", 1)[0].strip()
        variables[key.strip()] = value
    return variables


def _parse_degrees(text: str, limit: Decimal, name: str) -> float:
    value = _decimal(text)
    if value is None or abs(value) > limit:
        # The value itself never appears in the message.
        message = f"{name} is not a decimal number in range"
        raise SetupError(message)
    return float(value)


def denylist_entries(lat_text: str, lon_text: str) -> list[str]:
    """Return the denylist entries for one coordinate pair.

    The entries are the raw strings, then the pair at two to six decimals in both orders
    with each separator (comma, comma and space, space).

    Args:
        lat_text: The latitude as written.
        lon_text: The longitude as written.

    Returns:
        Unique entries, at least ``MIN_ENTRY_LENGTH`` characters each.
    """
    lat = _parse_degrees(lat_text, MAX_LATITUDE, "HOME_LAT")
    lon = _parse_degrees(lon_text, MAX_LONGITUDE, "HOME_LON")
    entries = [lat_text.strip(), lon_text.strip()]
    for places in DENYLIST_PLACES:
        lat_rounded, lon_rounded = f"{lat:.{places}f}", f"{lon:.{places}f}"
        for first, second in ((lat_rounded, lon_rounded), (lon_rounded, lat_rounded)):
            entries.extend(f"{first}{separator}{second}" for separator in DENYLIST_SEPARATORS)
    return [entry for entry in dict.fromkeys(entries) if len(entry) >= MIN_ENTRY_LENGTH]


def _denylist_alternative(entry: str) -> bytes:
    """Match decimal coordinate values as numbers, other personal entries literally.

    A public forecast coordinate can share a prefix with a denylisted decimal but
    have a different value. Numeric boundaries prevent that false positive while
    normalized trailing zeros still detect the same private value at greater precision.
    This does not exempt any file or payload from the denylist.
    """
    if not re.fullmatch(r"[+-]?[0-9]{1,3}\.[0-9]+", entry):
        return re.escape(entry.encode("utf-8"))
    value = Decimal(entry)
    if abs(value) > MAX_LONGITUDE:
        return re.escape(entry.encode("utf-8"))
    unsigned = format(abs(value), "f").rstrip("0").rstrip(".")
    sign = b"-" if value < 0 else rb"\+?"
    if value == 0:
        sign = rb"[+-]?"
    number = re.escape(unsigned.encode("ascii"))
    number += rb"0*" if "." in unsigned else rb"(?:\.0+)?"
    return rb"(?<![0-9.+-])" + sign + number + rb"(?![0-9]|\.[0-9])"


def denylist_pattern(entries: Sequence[str]) -> re.Pattern[bytes] | None:
    """Compile the entries into one case-insensitive byte pattern.

    Args:
        entries: The denylist entries.

    Returns:
        The pattern, or None when there are no entries.
    """
    if not entries:
        return None
    alternatives = sorted({_denylist_alternative(entry) for entry in entries}, key=len)
    return re.compile(b"|".join(reversed(alternatives)), re.IGNORECASE)


def _in_range(first: Decimal, second: Decimal) -> bool:
    return (abs(first) <= MAX_LATITUDE and abs(second) <= MAX_LONGITUDE) or (
        abs(first) <= MAX_LONGITUDE and abs(second) <= MAX_LATITUDE
    )


def has_unlisted_coordinate(text: str, allowlist: Allowlist) -> bool:
    """Return whether one line holds a coordinate that is not an allowlisted landmark (R2).

    Args:
        text: One line of text, or one part of a file name.
        allowlist: The landmark coordinates.

    Returns:
        True when the line holds a pair or an assignment outside the allowlist.
    """
    for match in COORDINATE_PAIR.finditer(text):
        first, second = Decimal(match["first"]), Decimal(match["second"])
        listed = allowlist.allows_pair(first, second) or allowlist.allows_pair(second, first)
        if _in_range(first, second) and not listed:
            return True
    for match in COORDINATE_ASSIGNMENT.finditer(text):
        value = Decimal(match["value"])
        latitude = match["key"].lower().startswith("lat")
        limit = MAX_LATITUDE if latitude else MAX_LONGITUDE
        if abs(value) <= limit and not allowlist.allows_value(value, latitude=latitude):
            return True
    return False


def request_coordinates(url: str) -> list[tuple[str, str]]:
    """Return the ``(lat, lon)`` text of every coordinate a request URL carries (R3).

    Args:
        url: A recorded request URL.

    Returns:
        One pair per NWS ``/points/`` path, ``point`` parameter, and ``lat``/``lon`` (or
        ``latitude``/``longitude``) parameter pair; a missing half is an empty string.
    """
    parts = urlsplit(url)
    found = [(match["lat"], match["lon"]) for match in POINTS_PATH.finditer(unquote(parts.path))]
    query = parse_qs(parts.query, keep_blank_values=True)
    for value in query.get("point", []):
        lat, _, lon = value.partition(",")
        found.append((lat, lon))
    for lat_key, lon_key in (("lat", "lon"), ("latitude", "longitude")):
        found.extend(
            zip_longest(query.get(lat_key, []), query.get(lon_key, []), fillvalue=""),
        )
    return found


def _url_is_allowed(url: str, allowlist: Allowlist) -> bool:
    for lat_text, lon_text in request_coordinates(url):
        lat, lon = _decimal(lat_text), _decimal(lon_text)
        if lat is None or lon is None or not allowlist.allows_pair(lat, lon):
            return False
    return True


def _manifest_lines(text: str, allowlist: Allowlist) -> list[int]:
    flagged: list[int] = []
    for number, line in enumerate(text.split("\n"), start=1):
        for match in URL_FIELD.finditer(line):
            try:
                url: object = json.loads(match["literal"])
            except json.JSONDecodeError:
                url = None
            if not isinstance(url, str) or not _url_is_allowed(url, allowlist):
                flagged.append(number)
                break
    return flagged


def is_manifest(path: str) -> bool:
    """Return whether a repository path is a fixture manifest, which R3 reads.

    Args:
        path: A repository-relative POSIX path.

    Returns:
        True for ``manifest.json`` or ``*-manifest.json`` under ``tests/fixtures/``.
    """
    name = path.rsplit("/", 1)[-1]
    return path.startswith(FIXTURE_TREE) and (
        name == MANIFEST_NAME or name.endswith(MANIFEST_SUFFIX)
    )


def is_env_file(path: str) -> bool:
    """Return whether a path names an environment file (R4).

    Args:
        path: A repository-relative POSIX path.

    Returns:
        True for ``.env``, ``*.env``, and ``.env.*``.
    """
    name = path.rsplit("/", 1)[-1]
    return name == ".env" or name.endswith(".env") or name.startswith(".env.")


def _line_numbers(data: bytes, pattern: re.Pattern[bytes]) -> list[int]:
    return sorted({data.count(b"\n", 0, match.start()) + 1 for match in pattern.finditer(data)})


def _decompress(data: bytes) -> bytes | None:
    """Return the decompressed bytes of a gzip file, or None when they cannot be read."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            payload = stream.read(MAX_DECOMPRESSED_BYTES + 1)
    except (OSError, EOFError, zlib.error):
        return None
    return payload if len(payload) <= MAX_DECOMPRESSED_BYTES else None


@dataclass(frozen=True)
class Scanner:
    """Applies the rules to files under one root directory."""

    root: Path
    allowlist: Allowlist
    denylist: re.Pattern[bytes] | None

    def scan(self, paths: Iterable[str]) -> list[Finding]:
        """Scan files and return every finding, sorted by path, line, and rule.

        Args:
            paths: File paths relative to ``root`` (or absolute).

        Returns:
            The findings.
        """
        findings: set[Finding] = set()
        for path in dict.fromkeys(self.relative(path) for path in paths):
            findings.update(self.scan_file(path))
        return sorted(findings)

    def relative(self, path: str) -> str:
        """Return ``path`` as a POSIX path relative to ``root`` where it lies under it.

        Args:
            path: A path as given on the command line or by ``git ls-files``.

        Returns:
            The normalized path.
        """
        candidate = Path(path)
        if candidate.is_absolute() and candidate.resolve().is_relative_to(self.root.resolve()):
            candidate = candidate.resolve().relative_to(self.root.resolve())
        return candidate.as_posix()

    def _shown_path(self, path: str) -> tuple[str, set[str]]:
        rules: set[str] = set()
        shown: list[str] = []
        for part in path.split("/"):
            hits: set[str] = set()
            if self.denylist is not None and self.denylist.search(part.encode("utf-8")):
                hits.add("R1")
            if has_unlisted_coordinate(part, self.allowlist):
                hits.add("R2")
            rules |= hits
            shown.append(REDACTED if hits else part)
        return "/".join(shown), rules

    def scan_file(self, path: str) -> set[Finding]:
        """Apply every rule to one file.

        Args:
            path: A POSIX path relative to ``root``.

        Returns:
            The file's findings; none for a file that does not exist.

        Raises:
            SetupError: The file exists but cannot be read.
        """
        shown, name_rules = self._shown_path(path)
        findings = {
            Finding(shown, 0, rule, "the file name holds a personal value") for rule in name_rules
        }
        if is_env_file(path):
            findings.add(Finding(shown, 0, "R4", "environment file"))
        try:
            data = (self.root / path).read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            return findings
        except OSError as error:
            message = f"cannot read {shown}"
            raise SetupError(message) from error
        findings |= self._denylist_findings(shown, data)
        if b"\0" in data[:BINARY_SNIFF_BYTES]:
            return findings
        text = data.decode("utf-8", errors="replace")
        if not path.startswith(PAYLOAD_TREES):
            findings.update(
                Finding(shown, number, "R2", "coordinate that is not an allowlisted landmark")
                for number, line in enumerate(text.split("\n"), start=1)
                if has_unlisted_coordinate(line, self.allowlist)
            )
        if is_manifest(path):
            findings.update(
                Finding(
                    shown, number, "R3", "request coordinate that is not an allowlisted landmark"
                )
                for number in _manifest_lines(text, self.allowlist)
            )
        return findings

    def _denylist_findings(self, shown: str, data: bytes) -> set[Finding]:
        if self.denylist is None:
            return set()
        findings = {
            Finding(shown, number, "R1", "denylist entry")
            for number in _line_numbers(data, self.denylist)
        }
        if data.startswith(GZIP_MAGIC):
            payload = _decompress(data)
            if payload is None:
                findings.add(Finding(shown, 0, "R1", "gzip payload could not be scanned"))
            else:
                findings.update(
                    Finding(shown, number, "R1", "denylist entry in the decompressed payload")
                    for number in _line_numbers(payload, self.denylist)
                )
        return findings


def tracked_files(root: Path) -> list[str]:
    """Return every file ``git ls-files`` lists under ``root``.

    Args:
        root: The repository root.

    Returns:
        Repository-relative POSIX paths.

    Raises:
        SetupError: git is missing or ``git ls-files`` fails.
    """
    git = shutil.which("git")
    if git is None:
        message = "git is not on PATH; --all lists the files with `git ls-files`"
        raise SetupError(message)
    completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell  # nosec B603
        [git, "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = "`git ls-files` failed; run --all inside the repository"
        raise SetupError(message)
    return [path for path in completed.stdout.decode("utf-8").split("\0") if path]


def synthetic_coordinates(
    landmarks: Sequence[Landmark],
    entries: Sequence[str],
    *,
    seed: int = SYNTHETIC_SEED,
) -> tuple[str, str]:
    """Generate a coordinate pair far from every landmark and clear of the denylist.

    The pair is deterministic for a given seed, landmarks, and denylist. No rendering of
    it contains a denylist entry, so planting it can never plant a personal value.

    Args:
        landmarks: The public landmarks to stay away from.
        entries: The denylist entries the pair must not contain.
        seed: The generator seed.

    Returns:
        The latitude and longitude, each with four decimals.

    Raises:
        SetupError: No candidate cleared the landmarks and the denylist.
    """
    # Synthetic test data, not a secret: a seeded generator keeps the self-test repeatable.
    generator = random.Random(seed)  # noqa: S311  # nosec B311
    lowered = [entry.lower() for entry in entries]
    for _ in range(SYNTHETIC_ATTEMPTS):
        lat = generator.uniform(*SYNTHETIC_LATITUDE_RANGE)
        lon = generator.uniform(*SYNTHETIC_LONGITUDE_RANGE)
        clear = all(
            max(abs(lat - float(item.lat)), abs(lon - float(item.lon)))
            >= SYNTHETIC_CLEARANCE_DEGREES
            for item in landmarks
        )
        lat_text, lon_text = f"{lat:.4f}", f"{lon:.4f}"
        renderings = f"{lat_text}, {lon_text}\n{lon_text}, {lat_text}\n{lat_text},{lon_text}"
        if clear and not any(entry in renderings for entry in lowered):
            return lat_text, lon_text
    message = "could not generate a synthetic coordinate pair clear of the denylist"
    raise SetupError(message)


@dataclass(frozen=True)
class _Probe:
    """One self-test rule: files that must fire it, files that must pass, values never shown."""

    rule: str
    planted: Mapping[str, bytes]
    clean: Mapping[str, bytes]
    secrets: Sequence[str]


def _probe_passes(scanner: Scanner, probe: _Probe) -> bool:
    for name, content in {**probe.planted, **probe.clean}.items():
        target = scanner.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    fired = scanner.scan(probe.planted)
    passed = scanner.scan(probe.clean)
    printed = "\n".join(str(finding) for finding in [*fired, *passed]).lower()
    return (
        any(finding.rule == probe.rule for finding in fired)
        and not any(finding.rule == probe.rule for finding in passed)
        and not any(secret.lower() in printed for secret in probe.secrets)
    )


def _probes(landmarks: Sequence[Landmark], entries: Sequence[str] | None) -> list[_Probe]:
    lat, lon = synthetic_coordinates(landmarks, entries or ())
    landmark = landmarks[0]
    probes: list[_Probe] = []
    if entries:
        first = entries[0]
        probes.append(
            _Probe(
                rule="R1",
                planted={"planted/denylisted.bin": b"\0\1 " + first.encode("utf-8") + b"\n"},
                clean={"clean/plain.bin": b"\0\1 nothing personal\n"},
                secrets=[first],
            )
        )
    probes.extend(
        [
            _Probe(
                rule="R2",
                planted={"planted/coordinates.txt": f"{lat}, {lon}\n".encode()},
                clean={"clean/landmark.txt": f"{landmark.lat}, {landmark.lon}\n".encode()},
                secrets=[lat, lon],
            ),
            _Probe(
                rule="R3",
                planted={
                    "tests/fixtures/recorded/planted/manifest.json": (
                        f'{{"url": "https://api.weather.gov/points/{lat},{lon}"}}\n'.encode()
                    )
                },
                clean={
                    "tests/fixtures/recorded/clean/manifest.json": (
                        "{"
                        f'"url": "https://api.weather.gov/points/{landmark.lat},{landmark.lon}"'
                        "}\n"
                    ).encode()
                },
                secrets=[lat, lon],
            ),
            _Probe(
                rule="R4",
                planted={"planted/.env": b"SELF_TEST=1\n"},
                clean={"clean/settings.toml": b"self_test = 1\n"},
                secrets=[],
            ),
        ]
    )
    return probes


RULE_NAMES = {
    "R1": "denylist",
    "R2": "coordinates",
    "R3": "request coordinates",
    "R4": "environment files",
}


def run_self_test(landmarks: Sequence[Landmark], entries: Sequence[str] | None) -> bool:
    """Plant samples in a temporary directory and prove each rule fires and redacts.

    Prints one PASS, FAIL, or SKIP line per rule and nothing else.

    Args:
        landmarks: The public landmarks; the first is the clean sample.
        entries: The denylist entries, or None in CI, where R1 is skipped.

    Returns:
        True when every rule that ran passed.
    """
    with tempfile.TemporaryDirectory(prefix="weatherbot-self-test-") as directory:
        scanner = Scanner(
            root=Path(directory),
            allowlist=Allowlist.from_landmarks(landmarks),
            denylist=denylist_pattern(entries or ()),
        )
        results = {
            probe.rule: _probe_passes(scanner, probe) for probe in _probes(landmarks, entries)
        }
    for rule, name in RULE_NAMES.items():
        if rule not in results:
            print(f"self-test {rule} {name}: SKIP (--ci: CI has no denylist)")
        else:
            print(f"self-test {rule} {name}: {'PASS' if results[rule] else 'FAIL'}")
    return all(results.values())


def _read_value(stream: TextIO) -> str:
    if stream.isatty():
        return getpass.getpass("Value to add to the denylist (not echoed): ")
    return stream.readline()


def _command_init(dotenv: Path) -> int:
    variables = read_dotenv(dotenv)
    missing = [key for key in ("HOME_LAT", "HOME_LON") if not variables.get(key, "").strip()]
    if missing:
        message = f"{dotenv.name} does not define {' and '.join(missing)}; add values with --add"
        raise SetupError(message)
    entries = denylist_entries(variables["HOME_LAT"], variables["HOME_LON"])
    added, total = add_entries(denylist_path(), entries)
    print(f"Wrote {added} new entries to the personal-data denylist ({total} in total).")
    return EXIT_CLEAN


def _command_add() -> int:
    value = _read_value(sys.stdin).strip()
    if len(value) < MIN_ENTRY_LENGTH or "\n" in value:
        message = f"a denylist value needs at least {MIN_ENTRY_LENGTH} characters on one line"
        raise SetupError(message)
    added, total = add_entries(denylist_path(), [value])
    if added:
        print(f"Added 1 entry to the personal-data denylist ({total} in total).")
    else:
        print("The personal-data denylist already holds that value.")
    return EXIT_CLEAN


def _required_entries() -> list[str]:
    entries = read_denylist(denylist_path())
    if not entries:
        raise SetupError(SETUP_INSTRUCTIONS)
    return entries


def _command_scan(files: Sequence[str], *, scan_all: bool, ci: bool) -> int:
    landmarks = load_landmarks()
    entries = None if ci else _required_entries()
    root = REPOSITORY_ROOT if scan_all else Path.cwd()
    paths = tracked_files(root) if scan_all else list(files)
    scanner = Scanner(
        root=root,
        allowlist=Allowlist.from_landmarks(landmarks),
        denylist=denylist_pattern(entries or ()),
    )
    findings = scanner.scan(paths)
    for finding in findings:
        print(finding)
    skipped = "; R1 skipped (--ci)" if ci else ""
    if findings:
        print(f"check_personal_data: {len(findings)} findings in {len(paths)} files{skipped}")
        return EXIT_FINDINGS
    print(f"check_personal_data: clean, {len(paths)} files scanned{skipped}")
    return EXIT_CLEAN


def _command_self_test(*, ci: bool) -> int:
    entries = None if ci else _required_entries()
    return EXIT_CLEAN if run_self_test(load_landmarks(), entries) else EXIT_FINDINGS


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="check_personal_data.py",
        description=(
            "Block personal data (the operator's coordinates and other denylisted values) "
            "from reaching the public repository. Output never shows a matched value."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--all", action="store_true", help="scan every file git tracks")
    mode.add_argument(
        "--self-test", action="store_true", help="prove the rules fire on planted samples"
    )
    mode.add_argument(
        "--init-from-env",
        metavar="PATH",
        type=Path,
        help="add HOME_LAT and HOME_LON from a dotenv file to the denylist; prints a count only",
    )
    mode.add_argument(
        "--add", action="store_true", help="add one value from standard input, never echoed"
    )
    parser.add_argument(
        "--ci", action="store_true", help="skip R1; set only in CI, which has no denylist"
    )
    parser.add_argument("files", nargs="*", metavar="FILE", help="files to scan")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        The exit status: 0 clean, 1 findings or a failed self-test, 2 a setup error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    files: list[str] = args.files
    scan_all: bool = args.all
    ci: bool = args.ci
    dotenv: Path | None = args.init_from_env
    adding: bool = args.add
    self_test: bool = args.self_test
    if files and (scan_all or self_test or dotenv or adding):
        parser.error("name files, or choose a mode, not both")
    if not files and not (scan_all or self_test or dotenv or adding):
        parser.error("name the files to scan, or pass --all")
    if ci and (dotenv or adding):
        parser.error("--ci applies to scans and the self-test only")
    try:
        if dotenv is not None:
            return _command_init(dotenv)
        if adding:
            return _command_add()
        if self_test:
            return _command_self_test(ci=ci)
        return _command_scan(files, scan_all=scan_all, ci=ci)
    except SetupError as error:
        print(f"check_personal_data: {error}", file=sys.stderr)
        return EXIT_SETUP
    except Exception as error:  # noqa: BLE001 - a traceback could echo a scanned value
        print(
            f"check_personal_data: internal error ({type(error).__name__}); the details are "
            "withheld so that no scanned value is echoed",
            file=sys.stderr,
        )
        return EXIT_SETUP


if __name__ == "__main__":
    raise SystemExit(main())
