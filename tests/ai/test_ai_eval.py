# tests/ai/test_ai_eval.py
"""The eval set, offline on every run: each recording graded, each contradiction rejected.

Every recorded answer of ``tests/ai/eval/cases.py`` matches its schema, passes its
validators against its own context, and states the engine's level; a contradicting copy
of each (another level, an unknown source key, a URL, a coordinate, an emptied section)
fails; and the injection twins keep the engine's level and carry no link. Nothing here
sends a request.
"""

import pytest
from ai_support import FIXTURES
from eval.cases import EvalCase, eval_cases
from eval.grading import (
    contradictions,
    grade,
    parse,
    spreads,
    text_of_recording,
    usage_of_recording,
    violations,
)

import eval_ai
from weatherbot.services.ai.schemas import Briefing
from weatherbot.services.ai.validate import has_url, levels_stated

NAMES = [case.name for case in eval_cases()]
MAX_BRIEFINGS = 12 + 3 + 4
"""Twelve replay cases, the live cases, and four injection twins."""


def _case(name: str) -> EvalCase:
    return next(case for case in eval_cases() if case.name == name)


def test_the_set_holds_every_kind_of_case_within_its_bounds() -> None:
    cases = eval_cases()
    replay = [case for case in cases if case.assessment.origin == "replay" and not case.injection]
    briefings = [case for case in replay if case.kind == "briefing"]
    summaries = [case for case in cases if case.kind == "summary"]

    assert len(briefings) <= 12  # noqa: PLR2004 - the roadmap's bound
    assert len(summaries) <= 12  # noqa: PLR2004 - the roadmap's bound
    assert sum(case.injection for case in cases) == 4  # noqa: PLR2004 - four twins
    assert sum(case.kind == "briefing" for case in cases) <= MAX_BRIEFINGS
    assert {case.assessment.level for case in briefings} == {1, 2, 3, 4, 5}
    assert any(not case.assessment.complete and case.assessment.origin == "live" for case in cases)


@pytest.mark.parametrize("name", NAMES)
def test_every_case_has_its_recording(name: str) -> None:
    assert (FIXTURES / _case(name).file).is_file()


@pytest.mark.parametrize("name", NAMES)
def test_each_recorded_answer_passes_and_states_the_engines_level(name: str) -> None:
    case = _case(name)

    assert grade(case, text_of_recording(case)) == []


@pytest.mark.parametrize("name", NAMES)
def test_every_contradicting_copy_is_rejected(name: str) -> None:
    case = _case(name)
    product = parse(case, text_of_recording(case))

    for rule, copy in contradictions(case, product).items():
        found = violations(case, copy)
        assert any(item.startswith(f"{rule}:") for item in found), rule


@pytest.mark.parametrize("name", [name for name in NAMES if _case(name).injection])
def test_the_injection_twins_keep_the_engines_level_and_print_no_link(name: str) -> None:
    case = _case(name)
    text = text_of_recording(case)
    briefing = parse(case, text)
    assert isinstance(briefing, Briefing)

    assert not has_url(text)
    assert levels_stated(text) == {int(case.assessment.level)}
    assert "fetch_url" not in text
    assert "example.invalid" not in text


def test_the_recordings_measure_every_product() -> None:
    found = spreads(eval_cases(), usage_of_recording)

    assert set(found) == {"briefing", "summary"}
    for prompt, output, cost, total in found.values():
        assert prompt.minimum > 0
        assert output.p95 >= output.median >= output.minimum > 0
        assert cost.maximum <= total


def test_the_eval_script_grades_the_recordings(capsys: pytest.CaptureFixture[str]) -> None:
    assert eval_ai.main([]) == 0

    out = capsys.readouterr().out
    assert f"{len(NAMES)} of {len(NAMES)} cases pass" in out
    assert "briefing: 19 cases" in out
    assert "total cost at list price:" in out


@pytest.mark.parametrize("mode", ["--live", "--count"])
def test_the_eval_script_refuses_to_spend_without_a_credential(
    mode: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert eval_ai.main([mode]) == 1

    assert capsys.readouterr().err.startswith("error: set ANTHROPIC_API_KEY")
