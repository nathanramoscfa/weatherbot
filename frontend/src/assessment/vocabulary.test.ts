// frontend/src/assessment/vocabulary.test.ts
import { QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  describeThreatLevel,
  ThreatLevelBadge,
} from "../app/ThreatLevelBadge.tsx";
import { createAppQueryClient } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import ladderFixture from "../test/fixtures/ladder.json";
import {
  FALLBACK_CODES,
  FALLBACK_EVENTS,
  FALLBACK_LADDER,
  FALLBACK_LEVELS,
  FALLBACK_RULES,
  FALLBACK_THRESHOLDS,
  levelActions,
  levelLabel,
  ruleSentence,
  setActiveLadder,
  useLadder,
} from "./vocabulary.ts";

const TYPED_LADDER = asSchema<components["schemas"]["LadderResponse"]>(
  ladderFixture satisfies JsonFixture<components["schemas"]["LadderResponse"]>,
);

describe("assessment vocabulary and ThreatLevelBadge names", () => {
  afterEach(() => {
    setActiveLadder(null);
    vi.restoreAllMocks();
  });

  it("matches the exported ladder.json fixture for all five levels, eleven rules, events, codes, and thresholds", () => {
    expect(FALLBACK_LADDER).toEqual(TYPED_LADDER);
    expect(FALLBACK_LEVELS).toEqual(TYPED_LADDER.levels);
    expect(FALLBACK_RULES).toEqual(TYPED_LADDER.rules);
    expect(FALLBACK_EVENTS).toEqual(TYPED_LADDER.events);
    expect(FALLBACK_CODES).toEqual(TYPED_LADDER.codes);
    expect(FALLBACK_THRESHOLDS).toEqual(TYPED_LADDER.thresholds);

    for (const lvl of TYPED_LADDER.levels) {
      expect(levelLabel(lvl.number)).toBe(lvl.label);
      expect(levelActions(lvl.number)).toBe(lvl.actions);
    }
    for (const rule of TYPED_LADDER.rules) {
      expect(ruleSentence(rule.id)).toBe(rule.sentence);
    }
  });

  it("gives ThreatLevelBadge the engine's exact level names when no custom label is passed", () => {
    const expectedLabels: ReadonlyArray<readonly [number, string]> = [
      [1, "All Clear"],
      [2, "Tropical Storm Threat"],
      [3, "Watch / Hurricane Threat"],
      [4, "Warning / Watch / Evacuation"],
      [5, "Hurricane Warning"],
    ];

    for (const [num, expected] of expectedLabels) {
      expect(describeThreatLevel(num).label).toBe(expected);
    }

    render(
      createElement(
        "div",
        null,
        createElement(ThreatLevelBadge, { level: 1 }),
        createElement(ThreatLevelBadge, { level: 2 }),
        createElement(ThreatLevelBadge, { level: 3 }),
        createElement(ThreatLevelBadge, { level: 4 }),
        createElement(ThreatLevelBadge, { level: 5 }),
      ),
    );

    for (const [, expected] of expectedLabels) {
      expect(screen.getByText(expected)).toBeInTheDocument();
    }

    expect(screen.queryByText("Awareness")).toBeNull();
    expect(screen.queryByText("Storm Watch")).toBeNull();
    expect(screen.queryByText("Hurricane Warning / Evacuation")).toBeNull();
    expect(
      screen.queryByText("Tropical Storm Warning / Hurricane Watch"),
    ).toBeNull();
  });

  it("reads /api/ladder through queryKeys.ladder() and returns fallback until the query resolves", async () => {
    const queryClient = createAppQueryClient();
    const customLadder: components["schemas"]["LadderResponse"] = {
      ...TYPED_LADDER,
      levels: TYPED_LADDER.levels.map((lvl) =>
        lvl.number === 3 ? { ...lvl, label: "Server Watch Label" } : lvl,
      ),
      rules: TYPED_LADDER.rules.map((rule) =>
        rule.id === "storm_cone"
          ? { ...rule, sentence: "Server cone sentence." }
          : rule,
      ),
    };

    vi.spyOn(apiClient, "GET").mockResolvedValue({
      data: customLadder,
      response: new Response(null, { status: 200 }),
    });

    const wrapper = ({ children }: { readonly children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    const { result } = renderHook(() => useLadder(), { wrapper });

    expect(queryKeys.ladder()).toEqual(["settings", "ladder"]);
    expect(result.current.levelLabel(3)).toBe("Watch / Hurricane Threat");

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.levelLabel(3)).toBe("Server Watch Label");
    expect(result.current.ruleSentence("storm_cone")).toBe(
      "Server cone sentence.",
    );
  });
});
