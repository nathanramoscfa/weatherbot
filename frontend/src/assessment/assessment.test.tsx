// frontend/src/assessment/assessment.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "../api/schema.ts";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import assessmentsFixture from "../test/fixtures/assessments.json";
import replayAssessmentFixture from "../test/fixtures/replay-assessment.json";
import { EvidenceList } from "./EvidenceList.tsx";
import { LevelSummary, UnavailableBanner } from "./LevelSummary.tsx";
import { LocationHero } from "./LocationHero.tsx";
import { OfficialProductList } from "./OfficialProductList.tsx";
import { ThreatMeter } from "./ThreatMeter.tsx";
import { ThreatTable } from "./ThreatTable.tsx";
import { WhyThisLevel } from "./WhyThisLevel.tsx";

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

describe("Extracted assessment components", () => {
  it("renders LocationHero, ThreatMeter, WhyThisLevel, LevelSummary, UnavailableBanner, and EvidenceList without inline styles", () => {
    const { container } = render(
      <div>
        <LocationHero
          assessment={TYPED_REPLAY_ASSESSMENT}
          timeZone={TYPED_REPLAY_ASSESSMENT.time_zone}
          origin="replay"
        />
        <ThreatMeter
          level={TYPED_REPLAY_ASSESSMENT.level.number}
          complete={TYPED_REPLAY_ASSESSMENT.complete}
        />
        <WhyThisLevel
          assessment={TYPED_REPLAY_ASSESSMENT}
          insideNwsCoverage={TYPED_REPLAY_ASSESSMENT.inside_nws_coverage}
          timeZone={TYPED_REPLAY_ASSESSMENT.time_zone}
          breakpointSpan={TYPED_REPLAY_ASSESSMENT.breakpoint_span}
        >
          <LevelSummary assessment={TYPED_REPLAY_ASSESSMENT}>
            <EvidenceList
              evidence={TYPED_REPLAY_ASSESSMENT.evidence}
              timeZone={TYPED_REPLAY_ASSESSMENT.time_zone}
            />
          </LevelSummary>
        </WhyThisLevel>
        <UnavailableBanner
          complete={TYPED_REPLAY_ASSESSMENT.complete}
          unavailable={TYPED_REPLAY_ASSESSMENT.unavailable}
        />
      </div>,
    );

    expect(
      screen.getByTestId("location-hero-headline"),
    ).toHaveTextContent("At least Level 5 — Hurricane Warning");
    expect(
      screen.getAllByText(
        /At least: the level is a floor because these inputs were unavailable:/i,
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("hurricane_warning")).toBeInTheDocument();
    expect(screen.getByText(/Deciding evidence/i)).toBeInTheDocument();
    expect(screen.getAllByText(/HWR/).length).toBeGreaterThan(0);
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("renders OfficialProductList and ThreatTable for live and replay assessments", () => {
    const miami = TYPED_ASSESSMENTS.locations[0]!;
    const assessment = miami.assessment!;
    const { container } = render(
      <div>
        <OfficialProductList
          official={assessment.official}
          timeZone={miami.time_zone}
        />
        <ThreatTable
          threats={TYPED_REPLAY_ASSESSMENT.threats}
          windProbabilities={TYPED_REPLAY_ASSESSMENT.wind_probabilities}
          asOf={TYPED_REPLAY_ASSESSMENT.as_of}
          timeZone={TYPED_REPLAY_ASSESSMENT.time_zone}
        />
      </div>,
    );

    expect(
      screen.getByText(/Covering official products/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /County-zone alerts outside this location's zones \(context only; never sets the level\)/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Storm threats/i)).toBeInTheDocument();
    expect(screen.getByText(/Dorian \(AL052019\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/5 km wind-speed probabilities/i),
    ).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();
  });
});
