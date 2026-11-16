// frontend/src/app/navStatus.test.ts
import { describe, expect, it } from "vitest";
import type { components } from "../api/schema.ts";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import { aiStatus, TYPED_AI } from "../test/ai.ts";
import alertsFixture from "../test/fixtures/alerts.json";
import assessmentsFixture from "../test/fixtures/assessments.json";
import healthFixture from "../test/fixtures/health.json";
import stormsFixture from "../test/fixtures/storms.json";
import { deriveNavBadges } from "./navStatus.ts";

type Schemas = components["schemas"];

const ASSESSMENTS = asSchema<Schemas["AssessmentsResponse"]>(
  assessmentsFixture satisfies JsonFixture<Schemas["AssessmentsResponse"]>,
);
const STORMS = asSchema<Schemas["StormsResponse"]>(
  stormsFixture satisfies JsonFixture<Schemas["StormsResponse"]>,
);
const ALERTS = asSchema<Schemas["AlertsResponse"]>(
  alertsFixture satisfies JsonFixture<Schemas["AlertsResponse"]>,
);
const HEALTH = asSchema<Schemas["HealthResponse"]>(
  healthFixture satisfies JsonFixture<Schemas["HealthResponse"]>,
);

function withLevel(
  response: Schemas["AssessmentsResponse"],
  index: number,
  level: Schemas["ThreatLevelResponse"],
): Schemas["AssessmentsResponse"] {
  return {
    ...response,
    locations: response.locations.map((item, idx) =>
      idx === index && item.assessment
        ? { ...item, assessment: { ...item.assessment, level } }
        : item,
    ),
  };
}

describe("deriveNavBadges", () => {
  it("reads the highest level, the storm count, and the covering alerts from the shared queries", () => {
    const badges = deriveNavBadges({
      assessments: ASSESSMENTS,
      storms: STORMS,
      alerts: ALERTS,
      ai: TYPED_AI,
      health: { ...HEALTH, stale: false },
    });
    expect(badges["/"]).toEqual({
      tone: "level",
      level: 1,
      text: "1",
      description: "Highest current level: 1, All Clear",
    });
    expect(badges["/storms"]).toEqual({
      tone: "count",
      text: "1",
      description: "1 active storm",
    });
    // The fixture's county-context alert does not cover the location.
    expect(badges["/alerts"]).toEqual({
      tone: "count",
      text: "1",
      description: "1 alert covers a watched location",
    });
    expect(badges["/ask"]).toBeUndefined();
    expect(badges["/settings"]).toBeUndefined();
  });

  it("names the highest of several levels, a non-ready AI state, and a stale monitor", () => {
    const assessments = withLevel(ASSESSMENTS, 1, {
      number: 5,
      label: "Hurricane Warning",
      actions: "Shelter if not evacuated",
    });
    const badges = deriveNavBadges({
      assessments,
      storms: { ...STORMS, storms: [] },
      alerts: { ...ALERTS, locations: [] },
      ai: aiStatus({ state: "paused" }),
      health: { ...HEALTH, stale: true },
    });
    expect(badges["/"]).toMatchObject({
      level: 5,
      text: "5",
      description: "Highest current level: 5, Hurricane Warning",
    });
    expect(badges["/storms"]).toBeUndefined();
    expect(badges["/alerts"]).toBeUndefined();
    expect(badges["/ask"]).toEqual({
      tone: "ai",
      text: "Paused",
      description: "AI is paused",
    });
    expect(badges["/settings"]).toEqual({
      tone: "warning",
      text: "!",
      description: "The monitor's data is stale",
    });
  });

  it("shows nothing before the queries answer and falls back to health's AI state", () => {
    expect(deriveNavBadges({})).toEqual({});
    const badges = deriveNavBadges({
      health: { ...HEALTH, stale: false, ai: { ...HEALTH.ai, state: "capped" } },
    });
    expect(badges).toEqual({
      "/ask": { tone: "ai", text: "Capped", description: "AI is capped" },
    });
  });
});
