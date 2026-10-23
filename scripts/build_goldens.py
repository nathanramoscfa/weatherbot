# scripts/build_goldens.py
"""Build or check eight frozen replay timelines; approval is an explicit operator action.

First run writes candidates with null approvals. Review their transitions and the
calibration evidence in the PR. Only after the operator approves that specific review,
run --approve-date YYYY-MM-DD --review-sha256 SHA with the displayed review digest.
An existing approval is retained only when its timeline and metadata are unchanged.
"""

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import cast

from ladder_data import (
    CORPUS,
    GOLDENS,
    digest,
    entries,
    output_path,
    public_landmarks,
    replay_timelines,
)
from weatherbot.models import Thresholds
from weatherbot.services.replay import ReplayCorpus


def read_document(path: Path) -> dict[str, object]:
    """Read a golden document, rejecting a non-object JSON value."""
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        message = f"{path.name}: expected a golden object"
        raise TypeError(message)
    return cast("dict[str, object]", value)


def candidates() -> dict[str, dict[str, object]]:
    """Build all eight candidates through the production replay service."""
    corpus = ReplayCorpus.open(CORPUS)
    thresholds = Thresholds()
    manifest_sha = hashlib.sha256((CORPUS / "corpus-manifest.json").read_bytes()).hexdigest()
    found: dict[str, dict[str, object]] = {}
    for storm in corpus.storms():
        for landmark in public_landmarks():
            name = f"{storm.atcf_id}-{landmark}.json"
            timeline = entries(replay_timelines()[storm.atcf_id, landmark])
            found[name] = {
                "_file": f"tests/golden/replay/{name}",
                "atcf_id": storm.atcf_id,
                "archive_name": storm.name,
                "landmark": landmark,
                "manifest_sha256": manifest_sha,
                "ruleset": thresholds.fingerprint(),
                "timeline": timeline,
                "approval": None,
            }
    return found


def review_digest(documents: dict[str, dict[str, object]]) -> str:
    """Bind the review to all eight candidates, including their source and ruleset hashes."""
    return digest(
        {
            name: {key: value for key, value in document.items() if key != "approval"}
            for name, document in documents.items()
        }
    )


def approved(document: dict[str, object]) -> bool:
    """Check both the approval date and its digest of the exact timeline."""
    record = document.get("approval")
    if not isinstance(record, dict):
        return False
    approval = cast("dict[str, object]", record)
    try:
        day = date.fromisoformat(str(approval["date"]))
    except (KeyError, ValueError):
        return False
    return day.isoformat() == approval["date"] and approval.get("timeline_sha256") == digest(
        document["timeline"]
    )


def review(documents: dict[str, dict[str, object]]) -> str:
    """Render every level/rule transition, with the covering official codes, as Markdown."""
    lines: list[str] = []
    for document in documents.values():
        lines += [
            f"### {document['archive_name']} ({document['atcf_id']}) — {document['landmark']}",
            "",
            "| Advisory | Issued UTC | Level | Rule | Covering codes |",
            "| --- | --- | --- | --- | --- |",
        ]
        previous: tuple[object, object] | None = None
        for row in cast("list[dict[str, object]]", document["timeline"]):
            state = (row["level"], row["rule"])
            if state == previous:
                continue
            codes = ", ".join(cast("list[str]", row["official_codes"])) or "—"
            lines.append(
                f"| {row['advisory']} | {row['issued_at']} | {row['level']} | "
                f"{row['rule']} | {codes} |"
            )
            previous = state
        lines.append("")
    lines += [f"Review SHA-256: `{review_digest(documents)}`", ""]
    return "\n".join(lines)


def retain_approval(
    candidate: dict[str, object], existing: dict[str, object] | None, day: date | None
) -> dict[str, object]:
    """Retain an unchanged approval or attach a newly authorized one; refuse a silent edit.

    Raises:
        ValueError: A frozen golden changed without a fresh approval.
    """
    updated = dict(candidate)
    if day is not None:
        updated["approval"] = {
            "date": day.isoformat(),
            "timeline_sha256": digest(candidate["timeline"]),
        }
    elif existing is not None and existing.get("approval") is not None:
        same = {k: v for k, v in existing.items() if k != "approval"} == {
            k: v for k, v in candidate.items() if k != "approval"
        }
        if not same or not approved(existing):
            message = "a frozen golden requires a new operator approval"
            raise ValueError(message)
        updated["approval"] = existing["approval"]
    return updated


def main(argv: list[str] | None = None) -> int:
    """Build candidates, check frozen files, or record an operator-authorized approval."""
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--review-only", action="store_true")
    action.add_argument("--approve-date", type=date.fromisoformat)
    parser.add_argument("--review-sha256")
    args = parser.parse_args(argv)
    if bool(args.approve_date) != bool(args.review_sha256) or (args.check and args.approve_date):
        parser.error("approval needs both --approve-date and --review-sha256; --check never writes")
    documents = candidates()
    if args.approve_date and args.review_sha256 != review_digest(documents):
        parser.error("review digest differs; review the current candidates before approval")
    if args.review_only:
        print(review(documents))
        return 0
    expected_names = set(documents)
    existing_names = {path.name for path in GOLDENS.glob("*.json")}
    failures = sorted(existing_names - expected_names)
    for name, candidate in documents.items():
        path = output_path(GOLDENS / name, GOLDENS)
        existing = read_document(path) if path.is_file() else None
        same = existing is not None and {k: v for k, v in existing.items() if k != "approval"} == {
            k: v for k, v in candidate.items() if k != "approval"
        }
        if args.check:
            if not same or existing is None or not approved(existing):
                failures.append(name)
            continue
        try:
            updated = retain_approval(candidate, existing, args.approve_date)
        except ValueError:
            failures.append(name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name in failures:
        print(f"STALE or unapproved: tests/golden/replay/{name}")
    if failures:
        return 1
    print(f"OK {len(documents)} {'approved goldens checked' if args.check else 'goldens written'}")
    print(f"Review SHA-256: {review_digest(documents)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
