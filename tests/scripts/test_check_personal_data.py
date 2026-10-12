# tests/scripts/test_check_personal_data.py
"""Tests for the personal-data check, ``scripts/check_personal_data.py``.

Every planted value is synthetic and generated at run time, so this file holds no
coordinate the checker would flag when it scans the repository. Files are planted in the
temporary working directory, and ``WEATHERBOT_DENYLIST`` points at a denylist in
``tmp_path``, never at the operator's.
"""

import gzip
import io
import json
import sys
from pathlib import Path

import pytest

import check_personal_data as checker

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# scripts/public_landmarks.toml gives every coordinate to four decimals.
LANDMARK_DECIMALS = 4


@pytest.fixture
def landmarks() -> tuple[checker.Landmark, ...]:
    return checker.load_landmarks()


@pytest.fixture
def home(landmarks: tuple[checker.Landmark, ...]) -> tuple[str, str]:
    # A synthetic stand-in for the operator's coordinates.
    return checker.synthetic_coordinates(landmarks, (), seed=1)


@pytest.fixture
def planted(landmarks: tuple[checker.Landmark, ...], home: tuple[str, str]) -> tuple[str, str]:
    # A synthetic coordinate pair to plant, clear of the stand-in denylist.
    return checker.synthetic_coordinates(landmarks, checker.denylist_entries(*home))


@pytest.fixture
def denylist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: tuple[str, str]) -> Path:
    path = tmp_path / "config" / "personal-denylist.txt"
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(path))
    checker.add_entries(path, checker.denylist_entries(*home))
    return path


def write(path: str, content: str | bytes) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_bytes(content)
    return path


def manifest(url: str) -> str:
    return json.dumps({"schema": 1, "captures": [{"file": "payload.json", "url": url}]}, indent=2)


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    status = checker.main(list(args))
    captured = capsys.readouterr()
    return status, captured.out + captured.err


# Rule R1 flags denylist entries.


def test_r1_fires_on_a_denylist_entry_in_text_and_binary_files(
    denylist: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = checker.read_denylist(denylist)[2]
    text = write("notes/text.md", f"first line\nsee {entry} here\n")
    blob = write("tests/fixtures/recorded/source/2026-10-20/blob.bin", b"\0\1" + entry.encode())

    status, output = run(capsys, text, blob)

    assert status == checker.EXIT_FINDINGS
    assert "notes/text.md:2: R1" in output
    assert "tests/fixtures/recorded/source/2026-10-20/blob.bin:1: R1" in output


def test_r1_passes_a_clean_file(denylist: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert denylist.exists()
    clean = write("notes/clean.md", "nothing personal here\n")

    assert run(capsys, clean)[0] == checker.EXIT_CLEAN


def test_r1_scans_a_gzip_payload_decompressed(
    denylist: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = checker.read_denylist(denylist)[0]
    payload = gzip.compress(f'{{\n  "near": "{entry}"\n}}\n'.encode(), mtime=0)
    path = write("tests/fixtures/replay/storm/cone.geojson.gz", payload)

    status, output = run(capsys, path)

    assert status == checker.EXIT_FINDINGS
    assert "cone.geojson.gz:2: R1 denylist entry in the decompressed payload" in output


def test_r1_matches_regardless_of_letter_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "denylist.txt"
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(path))
    checker.add_entries(path, ["Synthetic Example Lane"])
    notes = write("notes.md", "it is on SYNTHETIC example lane\n")

    status, output = run(capsys, notes)

    assert status == checker.EXIT_FINDINGS
    assert "notes.md:1: R1" in output


# Rule R2 flags coordinates that are not landmarks.


@pytest.mark.parametrize(
    "template",
    [
        "{lat}, {lon}",
        "{lon},{lat}",
        "{lat} {lon}",
        "near {lat}, {lon}.",
        "[{lon}, {lat}]",
        "lat = {lat}",
        '"longitude": {lon}',
        "HOME_LAT={lat}",
        "homeLat: '{lat}'",
        "?lat={lat}&lon={lon}",
    ],
)
def test_r2_fires_on_a_coordinate_pair_or_assignment(
    planted: tuple[str, str], template: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lat, lon = planted
    sample = write("docs/sample.md", "title\n" + template.format(lat=lat, lon=lon) + "\n")

    status, output = run(capsys, "--ci", sample)

    assert status == checker.EXIT_FINDINGS
    assert "docs/sample.md:2: R2" in output


@pytest.mark.parametrize(
    "template",
    [
        "{lat}, {lon}",
        "{lon},{lat}",
        "{lat} {lon}",
        "lat = {lat}\nlon = {lon}",
        '{{"latitude": {lat}, "longitude": {lon}}}',
    ],
)
@pytest.mark.parametrize("places", [4, 3])
def test_r2_passes_every_landmark(
    landmarks: tuple[checker.Landmark, ...],
    template: str,
    places: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    samples = [
        write(
            f"docs/{item.key}.md",
            template.format(lat=f"{item.lat:.{places}f}", lon=f"{item.lon:.{places}f}") + "\n",
        )
        for item in landmarks
    ]

    assert run(capsys, "--ci", *samples)[0] == checker.EXIT_CLEAN


def test_a_landmark_matches_within_half_a_unit_of_the_third_decimal() -> None:
    allowlist = checker.Allowlist.from_landmarks(checker.load_landmarks())
    step = checker.LANDMARK_TOLERANCE

    for lat, lon in allowlist.pairs:
        assert allowlist.allows_pair(lat + step, lon - step)
        assert not allowlist.allows_pair(lat + step * 3, lon)


@pytest.mark.parametrize(
    "text",
    [
        "version 1.2.345 and 6.789",
        "pyright>=1.1.414",
        "a ratio of 123.456, 98.765",
        "two decimals: 10.25, 20.75",
        "timestamp 1730000000.123 0.456",
        "flat = 1.234",
        "translate: 12.345",
    ],
)
def test_r2_ignores_numbers_that_are_not_coordinates(
    text: str, capsys: pytest.CaptureFixture[str]
) -> None:
    sample = write("docs/numbers.md", text + "\n")

    assert run(capsys, "--ci", sample)[0] == checker.EXIT_CLEAN


def test_r2_skips_the_noaa_payload_trees_but_not_other_fixtures(
    planted: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    lat, lon = planted
    body = f"[{lon}, {lat}]\n"
    recorded = write("tests/fixtures/recorded/nhc-current-storms/2026-10-20/storm.json", body)
    replay = write("tests/fixtures/replay/al092022/cone.json", body)
    other = write("tests/fixtures/other/sample.json", body)

    assert run(capsys, "--ci", recorded, replay)[0] == checker.EXIT_CLEAN
    status, output = run(capsys, "--ci", other)
    assert status == checker.EXIT_FINDINGS
    assert "tests/fixtures/other/sample.json:1: R2" in output


# Rule R3 flags request coordinates in fixture manifests.


URL_TEMPLATES = [
    "https://api.weather.gov/points/{lat},{lon}",
    "https://api.weather.gov/alerts/active?point={lat},{lon}",
    "https://api.weather.gov/alerts/active?point={lat}%2C{lon}",
    "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}",
]


@pytest.mark.parametrize("template", URL_TEMPLATES)
def test_r3_fires_on_a_manifest_url_with_a_non_landmark_coordinate(
    planted: tuple[str, str], template: str, capsys: pytest.CaptureFixture[str]
) -> None:
    url = template.format(lat=planted[0], lon=planted[1])
    path = write("tests/fixtures/recorded/nws-points/2026-10-20/manifest.json", manifest(url))

    status, output = run(capsys, "--ci", path)

    assert status == checker.EXIT_FINDINGS
    assert "nws-points/2026-10-20/manifest.json:6: R3" in output
    assert ": R2" not in output


@pytest.mark.parametrize("template", URL_TEMPLATES)
def test_r3_passes_a_manifest_url_with_a_landmark(
    landmarks: tuple[checker.Landmark, ...], template: str, capsys: pytest.CaptureFixture[str]
) -> None:
    landmark = landmarks[0]
    url = template.format(lat=landmark.lat, lon=landmark.lon)
    path = write("tests/fixtures/recorded/nws-points/2026-10-20/manifest.json", manifest(url))

    assert run(capsys, "--ci", path)[0] == checker.EXIT_CLEAN


def test_r3_fails_closed_on_a_coordinate_it_cannot_pair(
    landmarks: tuple[checker.Landmark, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    url = f"https://nominatim.openstreetmap.org/reverse?lat={landmarks[0].lat}"
    path = write("tests/fixtures/recorded/nominatim/2026-10-20/manifest.json", manifest(url))

    assert run(capsys, "--ci", path)[0] == checker.EXIT_FINDINGS


def test_r3_reads_only_fixture_manifests(
    planted: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    url = "https://api.weather.gov/points/{},{}".format(*planted)
    path = write("docs/manifest.json", json.dumps({"note": "an example", "url": url}))

    status, output = run(capsys, "--ci", path)

    assert status == checker.EXIT_FINDINGS
    assert ": R3" not in output


# Rule R4 flags environment files.


@pytest.mark.parametrize("name", [".env", "deploy/production.env", "config/.env.local"])
def test_r4_fires_on_an_environment_file(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(name, "SETTING=1\n")

    status, output = run(capsys, "--ci", path)

    assert status == checker.EXIT_FINDINGS
    assert f"{name}:0: R4" in output


@pytest.mark.parametrize("name", ["docs/environment.md", "src/env.py", "settings.toml"])
def test_r4_passes_other_files(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(name, "setting = 1\n")

    assert run(capsys, "--ci", path)[0] == checker.EXIT_CLEAN


# The output never shows a matched value.


def test_the_output_never_contains_a_planted_value(
    denylist: Path, planted: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    entries = checker.read_denylist(denylist)
    lat, lon = planted
    files = [
        write("docs/notes.md", f"{entries[0]}\n{lat}, {lon}\nlatitude = {lat}\n"),
        write(
            "tests/fixtures/recorded/nws-points/2026-10-20/manifest.json",
            manifest(f"https://api.weather.gov/points/{lat},{lon}"),
        ),
        write(f"notes/{lat},{lon}.txt", "named after a place\n"),
        write(f"notes/{entries[0]}/readme.md", "in a directory named after a place\n"),
    ]

    status, output = run(capsys, *files)

    assert status == checker.EXIT_FINDINGS
    for rule in ("R1", "R2", "R3"):
        assert f": {rule} " in output
    assert f"notes/{checker.REDACTED}:0: R2" in output
    assert f"notes/{checker.REDACTED}/readme.md:0: R1" in output
    for value in [*entries, lat, lon]:
        assert value not in output


def test_a_setup_error_never_echoes_a_dotenv_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(tmp_path / "denylist.txt"))
    dotenv = tmp_path / "synthetic.env"
    dotenv.write_text("HOME_LAT=not-a-number-qzx\nHOME_LON=also-wrong-qzx\n", encoding="utf-8")

    status, output = run(capsys, "--init-from-env", str(dotenv))

    assert status == checker.EXIT_SETUP
    assert "HOME_LAT" in output
    assert "qzx" not in output


# The denylist fails closed, and two commands fill it.


def test_a_missing_denylist_fails_closed_without_ci(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(tmp_path / "absent.txt"))
    clean = write("notes.md", "nothing personal here\n")

    status, output = run(capsys, clean)
    assert status == checker.EXIT_SETUP
    assert "--init-from-env" in output

    assert run(capsys, "--self-test")[0] == checker.EXIT_SETUP
    assert run(capsys, "--ci", clean)[0] == checker.EXIT_CLEAN


def test_an_empty_denylist_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "denylist.txt"
    path.write_text(checker.DENYLIST_HEADER + "\n", encoding="utf-8")
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(path))
    clean = write("notes.md", "nothing personal here\n")

    assert run(capsys, clean)[0] == checker.EXIT_SETUP


def test_a_denylist_inside_the_repository_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(REPOSITORY_ROOT / "personal-denylist.txt"))
    clean = write("notes.md", "nothing personal here\n")

    status, output = run(capsys, clean)

    assert status == checker.EXIT_SETUP
    assert "outside the repository" in output


def test_init_from_env_writes_entries_and_prints_only_a_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home: tuple[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "config" / "personal-denylist.txt"
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(path))
    lat, lon = home
    dotenv = tmp_path / "synthetic.env"
    dotenv.write_text(
        f'# synthetic\nexport HOME_LAT="{lat}"\nHOME_LON={lon}  # inline comment\nOTHER=\n',
        encoding="utf-8",
    )
    expected = checker.denylist_entries(lat, lon)

    status, output = run(capsys, "--init-from-env", str(dotenv))

    assert status == checker.EXIT_CLEAN
    assert f"Wrote {len(expected)} new entries" in output
    assert lat not in output
    assert lon not in output
    entries = checker.read_denylist(path)
    assert entries == expected
    assert {lat, lon, f"{lat}, {lon}", f"{lon},{lat}", f"{float(lat):.2f} {float(lon):.2f}"} <= set(
        entries
    )
    assert path.read_text(encoding="utf-8").startswith(checker.DENYLIST_HEADER)

    status, output = run(capsys, "--init-from-env", str(dotenv))
    assert status == checker.EXIT_CLEAN
    assert "Wrote 0 new entries" in output


def test_init_from_env_names_a_missing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(tmp_path / "denylist.txt"))
    dotenv = tmp_path / "synthetic.env"
    dotenv.write_text("HOME_LAT=\nUNRELATED=1\n", encoding="utf-8")

    status, output = run(capsys, "--init-from-env", str(dotenv))

    assert status == checker.EXIT_SETUP
    assert "HOME_LAT and HOME_LON" in output
    assert "--add" in output


def test_add_reads_one_value_from_standard_input_without_echoing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "denylist.txt"
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(path))
    value = "Synthetic Example Lane"
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{value}\n"))

    status, output = run(capsys, "--add")

    assert status == checker.EXIT_CLEAN
    assert value not in output
    assert checker.read_denylist(path) == [value]


def test_add_refuses_a_value_too_short_to_be_useful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "denylist.txt"
    monkeypatch.setenv(checker.DENYLIST_VARIABLE, str(path))
    monkeypatch.setattr(sys, "stdin", io.StringIO("abc\n"))

    assert run(capsys, "--add")[0] == checker.EXIT_SETUP
    assert not path.exists()


@pytest.mark.parametrize(
    ("environ", "windows", "parts"),
    [
        ({"APPDATA": "roaming"}, True, ("roaming",)),
        ({}, True, ("home", "AppData", "Roaming")),
        ({"XDG_CONFIG_HOME": "xdg"}, False, ("xdg",)),
        ({}, False, ("home", ".config")),
    ],
)
def test_the_denylist_lives_in_the_user_configuration_directory(
    environ: dict[str, str], *, windows: bool, parts: tuple[str, ...]
) -> None:
    resolved = checker.resolve_denylist_path(environ, windows=windows, home=Path("home"))

    assert resolved == Path(*parts, "weatherbot", "personal-denylist.txt")


def test_the_override_variable_wins() -> None:
    environ = {checker.DENYLIST_VARIABLE: "elsewhere/list.txt", "APPDATA": "roaming"}

    resolved = checker.resolve_denylist_path(environ, windows=True, home=Path("home"))

    assert resolved == Path("elsewhere/list.txt")


# The self-test and the allowlist


def test_the_self_test_passes_and_prints_only_verdicts(
    denylist: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, output = run(capsys, "--self-test")

    assert status == checker.EXIT_CLEAN
    lines = output.splitlines()
    assert [line.split(":")[0] for line in lines] == [
        f"self-test {rule} {name}" for rule, name in checker.RULE_NAMES.items()
    ]
    assert all(line.endswith(": PASS") for line in lines)
    for value in checker.read_denylist(denylist):
        assert value not in output


def test_the_self_test_in_ci_skips_only_the_denylist(capsys: pytest.CaptureFixture[str]) -> None:
    status, output = run(capsys, "--self-test", "--ci")

    assert status == checker.EXIT_CLEAN
    lines = output.splitlines()
    assert lines[0].startswith("self-test R1 denylist: SKIP")
    assert all(line.endswith(": PASS") for line in lines[1:])


def test_the_landmark_allowlist_names_both_public_landmarks(
    landmarks: tuple[checker.Landmark, ...],
) -> None:
    assert {"miami-dade", "nassau"} <= {item.key for item in landmarks}
    for item in landmarks:
        assert item.name
        assert item.source.startswith("https://www.openstreetmap.org/")
        assert item.lat.as_tuple().exponent == -LANDMARK_DECIMALS
        assert item.lon.as_tuple().exponent == -LANDMARK_DECIMALS


def test_synthetic_coordinates_stay_clear_of_the_landmarks_and_the_denylist(
    landmarks: tuple[checker.Landmark, ...], home: tuple[str, str]
) -> None:
    entries = checker.denylist_entries(*home)

    lat, lon = checker.synthetic_coordinates(landmarks, entries)

    for item in landmarks:
        distance = max(abs(float(lat) - float(item.lat)), abs(float(lon) - float(item.lon)))
        assert distance >= checker.SYNTHETIC_CLEARANCE_DEGREES
    rendered = f"{lat}, {lon}\n{lon}, {lat}\n{lat},{lon}"
    assert not any(entry in rendered for entry in entries)


def test_all_mode_lists_the_tracked_files() -> None:
    tracked = checker.tracked_files(REPOSITORY_ROOT)

    assert "scripts/check_personal_data.py" in tracked
    assert "scripts/public_landmarks.toml" in tracked


@pytest.mark.parametrize(
    "args",
    [[], ["--all", "notes.md"], ["--add", "--ci"], ["--self-test", "--all"]],
)
def test_the_command_line_rejects_conflicting_arguments(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        checker.main(args)

    assert raised.value.code == checker.EXIT_SETUP
    assert "usage:" in capsys.readouterr().err
