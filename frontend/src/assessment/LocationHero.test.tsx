// frontend/src/assessment/LocationHero.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "../api/schema.ts";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import assessmentsFixture from "../test/fixtures/assessments.json";
import replayAssessmentFixture from "../test/fixtures/replay-assessment.json";
import { LocationHero } from "./LocationHero.tsx";
import {
  FALLBACK_CODES,
  FALLBACK_LADDER,
  FALLBACK_RULES,
  levelLabel,
} from "./vocabulary.ts";

const TYPED_ASSESSMENTS = asSchema<components["schemas"]["AssessmentsResponse"]>(
  assessmentsFixture satisfies JsonFixture<
    components["schemas"]["AssessmentsResponse"]
  >,
);
const TYPED_REPLAY_ASSESSMENT = asSchema<
  components["schemas"]["ReplayAssessmentResponse"]
>(
  replayAssessmentFixture satisfies JsonFixture<
    components["schemas"]["ReplayAssessmentResponse"]
  >,
);

const SNAKE_CASE_ID_PATTERN = /\b[a-z]+_[a-z_]+\b/;
const FORBIDDEN_CODE_PATTERN =
  /\b(HWR|TWR|HWA|TWA|TRW|TRA|FLZ\d+|FLC\d+|nhc-[a-z-]+|nws-[a-z-]+)\b/;
const RAW_UTC_PATTERN = /\b\d{4}-\d{2}-\d{2}\b|\bUTC\b/;

describe("LocationHero", () => {
  it("renders 'Level N — {engine name}', rule sentence, actions, meter, and relative age with local time, with zero snake_case rule ids, codes, source ids, zones, breakpoints, or raw UTC timestamps across all 11 rules", () => {
    const baseAssessment = TYPED_ASSESSMENTS.locations[0]!.assessment!;

    for (const rule of FALLBACK_RULES) {
      const expectedLabel = levelLabel(rule.level, FALLBACK_LADDER);
      const { container, unmount } = render(
        <LocationHero
          assessment={{
            ...baseAssessment,
            level: {
              number: rule.level,
              label: expectedLabel,
              actions:
                FALLBACK_LADDER.levels.find((l) => l.number === rule.level)
                  ?.actions ?? "Normal activities",
            },
            rule: rule.id,
            rule_trigger: rule.sentence,
            complete: true,
            unavailable: [],
          }}
          timeZone="America/New_York"
          ageSeconds={300}
        />,
      );

      const headline = screen.getByTestId("location-hero-headline");
      const sentence = screen.getByTestId("location-hero-sentence");
      const assessed = screen.getByTestId("location-hero-assessed");
      const hero = screen.getByTestId("location-hero");

      expect(headline).toHaveTextContent(
        `Level ${String(rule.level)} — ${expectedLabel}`,
      );
      expect(sentence).toHaveTextContent(rule.sentence);
      expect(assessed).toHaveTextContent(/Assessed 5 min old/);

      for (const target of [
        headline.textContent ?? "",
        sentence.textContent ?? "",
        hero.textContent ?? "",
      ]) {
        expect(target).not.toMatch(SNAKE_CASE_ID_PATTERN);
        expect(target).not.toMatch(FORBIDDEN_CODE_PATTERN);
        expect(target).not.toMatch(RAW_UTC_PATTERN);
        for (const codeItem of FALLBACK_CODES) {
          expect(target).not.toContain(codeItem.code);
        }
      }

      expect(container.querySelector("[style]")).toBeNull();
      unmount();
    }
  });

  it("prefixes 'At least' when incomplete and shows callouts for incomplete floor, toggle-changed note, evacuation order on, and replay", () => {
    const { container } = render(
      <LocationHero
        assessment={{
          ...TYPED_REPLAY_ASSESSMENT,
          complete: false,
          toggle_changed: true,
          toggle_note:
            "The evacuation-order toggle was changed after this assessment was stored; run a fresh check to assess with the updated toggle.",
        }}
        timeZone={TYPED_REPLAY_ASSESSMENT.time_zone}
        evacuationOrderOn
        origin="replay"
      />,
    );

    expect(screen.getByTestId("location-hero-headline")).toHaveTextContent(
      "At least Level 5 — Hurricane Warning",
    );
    expect(
      screen.getByTestId("location-hero-incomplete-callout"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("location-hero-toggle-callout"),
    ).toHaveTextContent(/changed after this assessment was stored/i);
    expect(
      screen.getByTestId("location-hero-evacuation-callout"),
    ).toHaveTextContent(/Evacuation order is on/i);
    expect(
      screen.getByTestId("location-hero-replay-callout"),
    ).toHaveTextContent(
      /manual evacuation-order toggle is off for a past storm/i,
    );
    expect(container.querySelector("[style]")).toBeNull();
  });
});
