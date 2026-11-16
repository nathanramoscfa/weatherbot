// frontend/src/assessment/vocabulary.ts
import { useQuery } from "@tanstack/react-query";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";

export type LadderResponse = components["schemas"]["LadderResponse"];
export type ThreatLevelResponse = components["schemas"]["ThreatLevelResponse"];
export type LadderRuleResponse = components["schemas"]["LadderRuleResponse"];
export type LadderEventResponse = components["schemas"]["LadderEventResponse"];
export type LadderCodeResponse = components["schemas"]["LadderCodeResponse"];
export type LadderThresholdResponse =
  components["schemas"]["LadderThresholdResponse"];

export const FALLBACK_LEVELS: ThreatLevelResponse[] = [
  {
    number: 1,
    label: "All Clear",
    actions: "Normal activities",
  },
  {
    number: 2,
    label: "Tropical Storm Threat",
    actions: "Monitor daily; review plans",
  },
  {
    number: 3,
    label: "Watch / Hurricane Threat",
    actions: "Stock supplies; pack; set an exit plan",
  },
  {
    number: 4,
    label: "Warning / Watch / Evacuation",
    actions: "Evacuate vulnerable areas; secure transport; assume routes close",
  },
  {
    number: 5,
    label: "Hurricane Warning",
    actions: "Shelter if not evacuated; expect outages; follow local orders",
  },
];

export const FALLBACK_RULES: LadderRuleResponse[] = [
  {
    order: 1,
    id: "hurricane_warning",
    level: 5,
    sentence: "A Hurricane Warning covers the location.",
    sources: ["NWS alerts", "NHC watch-warning segments"],
  },
  {
    order: 2,
    id: "tropical_storm_warning",
    level: 4,
    sentence: "A Tropical Storm Warning covers the location.",
    sources: ["NWS alerts", "NHC watch-warning segments"],
  },
  {
    order: 3,
    id: "hurricane_watch",
    level: 4,
    sentence: "A Hurricane Watch covers the location.",
    sources: ["NWS alerts", "NHC watch-warning segments"],
  },
  {
    order: 4,
    id: "evacuation_order",
    level: 4,
    sentence: "The operator's evacuation-order toggle is on.",
    sources: ["the location's evacuation-order toggle"],
  },
  {
    order: 5,
    id: "tropical_storm_watch",
    level: 3,
    sentence: "A Tropical Storm Watch covers the location.",
    sources: ["NWS alerts", "NHC watch-warning segments"],
  },
  {
    order: 6,
    id: "hurricane_cone",
    level: 3,
    sentence:
      "The location is inside the cone of a storm that is a hurricane at or before its closest approach, and that approach comes within the cone horizon.",
    sources: ["NHC cones", "NHC forecast points"],
  },
  {
    order: 7,
    id: "hurricane_wind_probability",
    level: 3,
    sentence:
      "The location's 64-kt wind-speed probability band starts at or above the hurricane wind floor.",
    sources: ["NHC 64-kt wind-speed probabilities"],
  },
  {
    order: 8,
    id: "storm_cone",
    level: 2,
    sentence: "The location is inside the cone of any active storm.",
    sources: ["NHC cones", "NHC forecast points"],
  },
  {
    order: 9,
    id: "development_region",
    level: 2,
    sentence:
      "The location is inside a seven-day potential development region whose chance is at least the development chance floor.",
    sources: ["NHC tropical weather outlook development regions"],
  },
  {
    order: 10,
    id: "tropical_storm_wind_probability",
    level: 2,
    sentence:
      "The location's 34-kt wind-speed probability band starts at or above the tropical-storm wind floor.",
    sources: ["NHC 34-kt wind-speed probabilities"],
  },
  {
    order: 11,
    id: "all_clear",
    level: 1,
    sentence: "No other rule matches.",
    sources: [],
  },
];

export const FALLBACK_EVENTS: LadderEventResponse[] = [
  {
    event: "Hurricane Warning",
    rule: "hurricane_warning",
    level: 5,
  },
  {
    event: "Tropical Storm Warning",
    rule: "tropical_storm_warning",
    level: 4,
  },
  {
    event: "Hurricane Watch",
    rule: "hurricane_watch",
    level: 4,
  },
  {
    event: "Tropical Storm Watch",
    rule: "tropical_storm_watch",
    level: 3,
  },
];

export const FALLBACK_CODES: LadderCodeResponse[] = [
  {
    code: "HWR",
    name: "Hurricane Warning",
    rule: "hurricane_warning",
    level: 5,
  },
  {
    code: "TWR",
    name: "Tropical Storm Warning",
    rule: "tropical_storm_warning",
    level: 4,
  },
  {
    code: "HWA",
    name: "Hurricane Watch",
    rule: "hurricane_watch",
    level: 4,
  },
  {
    code: "TWA",
    name: "Tropical Storm Watch",
    rule: "tropical_storm_watch",
    level: 3,
  },
];

export const FALLBACK_THRESHOLDS: LadderThresholdResponse[] = [
  {
    name: "coastal_reach_km",
    value: 25,
    unit: "km",
    description: "How far a watch-warning segment reaches from its line.",
  },
  {
    name: "segment_end_tolerance_km",
    value: 5,
    unit: "km",
    description: "How far a segment reaches past its end.",
  },
  {
    name: "cone_horizon_h",
    value: 120,
    unit: "h",
    description:
      "How soon a hurricane's closest approach must come to be a threat.",
  },
  {
    name: "hurricane_wind_floor_pct",
    value: 10,
    unit: "%",
    description: "The lowest 64-kt band lower bound that is a threat.",
  },
  {
    name: "tropical_storm_wind_floor_pct",
    value: 5,
    unit: "%",
    description: "The lowest 34-kt band lower bound that is a threat.",
  },
  {
    name: "development_chance_floor_pct",
    value: 0,
    unit: "%",
    description: "The lowest seven-day development chance that is a threat.",
  },
];

export const FALLBACK_LADDER: LadderResponse = {
  levels: FALLBACK_LEVELS,
  rules: FALLBACK_RULES,
  events: FALLBACK_EVENTS,
  codes: FALLBACK_CODES,
  thresholds: FALLBACK_THRESHOLDS,
  ruleset: "c241a7ff882909314d943f1a18c64f056fd3a8fed706f5328bb7fe9a6a404226",
  notice:
    "Informational only; never a substitute for official guidance. See DISCLAIMER.md.",
};

let activeLadder: LadderResponse = FALLBACK_LADDER;

export function setActiveLadder(ladder?: LadderResponse | null): void {
  activeLadder = ladder ?? FALLBACK_LADDER;
}

function isLadderResponse(value: unknown): value is LadderResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<LadderResponse>;
  return (
    Array.isArray(candidate.levels) &&
    Array.isArray(candidate.rules) &&
    Array.isArray(candidate.events) &&
    Array.isArray(candidate.codes) &&
    Array.isArray(candidate.thresholds)
  );
}

export async function fetchLadder(): Promise<LadderResponse> {
  const { data, response } = await apiClient.GET("/api/ladder");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/ladder", response.status);
  }
  if (!isLadderResponse(data)) {
    return FALLBACK_LADDER;
  }
  activeLadder = data;
  return data;
}

export function levelLabel(
  levelNumber: number,
  ladder: LadderResponse = activeLadder,
): string {
  const normalized =
    levelNumber >= 5
      ? 5
      : levelNumber === 4
        ? 4
        : levelNumber === 3
          ? 3
          : levelNumber === 2
            ? 2
            : 1;
  const matched = ladder.levels.find((lvl) => lvl.number === normalized);
  if (matched) {
    return matched.label;
  }
  const fallback = FALLBACK_LEVELS.find((lvl) => lvl.number === normalized);
  return fallback?.label ?? "All Clear";
}

export function levelActions(
  levelNumber: number,
  ladder: LadderResponse = activeLadder,
): string {
  const normalized =
    levelNumber >= 5
      ? 5
      : levelNumber === 4
        ? 4
        : levelNumber === 3
          ? 3
          : levelNumber === 2
            ? 2
            : 1;
  const matched = ladder.levels.find((lvl) => lvl.number === normalized);
  if (matched) {
    return matched.actions;
  }
  const fallback = FALLBACK_LEVELS.find((lvl) => lvl.number === normalized);
  return fallback?.actions ?? "Normal activities";
}

export function ruleSentence(
  ruleId: string,
  ladder: LadderResponse = activeLadder,
): string {
  const matched = ladder.rules.find((rule) => rule.id === ruleId);
  if (matched) {
    return matched.sentence;
  }
  const fallback = FALLBACK_RULES.find((rule) => rule.id === ruleId);
  return fallback?.sentence ?? ruleId;
}

export function useLadder() {
  const query = useQuery({
    queryKey: queryKeys.ladder(),
    queryFn: fetchLadder,
  });
  const current = isLadderResponse(query.data) ? query.data : FALLBACK_LADDER;
  return {
    ...query,
    data: current,
    ladder: current,
    levels: current.levels,
    rules: current.rules,
    events: current.events,
    codes: current.codes,
    thresholds: current.thresholds,
    ruleset: current.ruleset,
    levelLabel: (n: number) => levelLabel(n, current),
    levelActions: (n: number) => levelActions(n, current),
    ruleSentence: (id: string) => ruleSentence(id, current),
  };
}
