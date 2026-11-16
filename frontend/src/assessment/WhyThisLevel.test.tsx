// frontend/src/assessment/WhyThisLevel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "../api/schema.ts";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import assessmentsFixture from "../test/fixtures/assessments.json";
import replayAssessmentFixture from "../test/fixtures/replay-assessment.json";
import { EvidenceList } from "./EvidenceList.tsx";
import { LevelSummary } from "./LevelSummary.tsx";
import { OfficialProductList } from "./OfficialProductList.tsx";
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

describe("WhyThisLevel", () => {
  it("renders a native <details> closed by default with every rule id, code, source id, zone, breakpoint span, UTC timestamp, and controls in the DOM and no [style]", () => {
    const miami = TYPED_ASSESSMENTS.locations[0]!;
    const { container } = render(
      <WhyThisLevel
        assessment={TYPED_REPLAY_ASSESSMENT}
        insideNwsCoverage={false}
        timeZone={TYPED_REPLAY_ASSESSMENT.time_zone}
        breakpointSpan={TYPED_REPLAY_ASSESSMENT.breakpoint_span}
        zones={["FLZ173", "FLC086"]}
        controls={
          <button type="button" role="switch" aria-checked="false">
            Evacuation order
          </button>
        }
      >
        <LevelSummary assessment={TYPED_REPLAY_ASSESSMENT}>
          <EvidenceList
            evidence={TYPED_REPLAY_ASSESSMENT.evidence}
            timeZone={TYPED_REPLAY_ASSESSMENT.time_zone}
          />
        </LevelSummary>
        <OfficialProductList
          official={miami.assessment!.official}
          timeZone={miami.time_zone}
        />
        <ThreatTable
          threats={TYPED_REPLAY_ASSESSMENT.threats}
          windProbabilities={TYPED_REPLAY_ASSESSMENT.wind_probabilities}
          asOf={TYPED_REPLAY_ASSESSMENT.as_of}
          timeZone={TYPED_REPLAY_ASSESSMENT.time_zone}
        />
      </WhyThisLevel>,
    );

    const details = screen.getByTestId("why-this-level");
    expect(details.tagName.toLowerCase()).toBe("details");
    expect(details).not.toHaveAttribute("open");
    expect(
      screen.getByText("Why this level / Official provenance & controls"),
    ).toBeInTheDocument();

    // Closed native <details> keeps rule id, codes, source id, zones, breakpoint span, UTC instant, and controls in DOM
    expect(screen.getByText("hurricane_warning")).toBeInTheDocument();
    expect(screen.getAllByText(/HWR/).length).toBeGreaterThan(0);
    expect(screen.getByText(/nhc-gis-archive/)).toBeInTheDocument();
    expect(screen.getByText(/Outside NWS coverage/)).toBeInTheDocument();
    expect(screen.getByText(/Bahamas \(NW\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/FLZ173/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/UTC/).length).toBeGreaterThan(0);
    expect(
      screen.getByText(TYPED_REPLAY_ASSESSMENT.snapshot_id),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();
  });
});
