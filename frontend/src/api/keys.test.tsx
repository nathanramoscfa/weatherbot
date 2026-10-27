// frontend/src/api/keys.test.tsx
import { describe, expect, it } from "vitest";
import {
  INVALIDATABLE_QUERY_KEYS,
  isInvalidatableQueryKey,
  queryKeys,
  STATIC_QUERY_KEYS,
} from "./keys.ts";

describe("query keys vocabulary", () => {
  it("matches the nine server-invalidatable query keys and keeps static keys separate", () => {
    expect(INVALIDATABLE_QUERY_KEYS).toEqual([
      "health",
      "locations",
      "assessments",
      "storms",
      "alerts",
      "map",
      "timeline",
      "notifications",
      "settings",
    ]);
    expect(STATIC_QUERY_KEYS).toEqual(["replay", "disclaimer", "licenses"]);

    for (const key of INVALIDATABLE_QUERY_KEYS) {
      expect(isInvalidatableQueryKey(key)).toBe(true);
    }
    for (const staticKey of STATIC_QUERY_KEYS) {
      expect(isInvalidatableQueryKey(staticKey)).toBe(false);
    }

    expect(queryKeys.health()).toEqual(["health"]);
    expect(queryKeys.timeline()).toEqual(["timeline"]);
    expect(queryKeys.timeline("Miami-Dade")).toEqual([
      "timeline",
      "Miami-Dade",
    ]);
    expect(queryKeys.replay()).toEqual(["replay"]);
    expect(queryKeys.replayAdvisory("AL112017", "025")).toEqual([
      "replay",
      "AL112017",
      "025",
    ]);
    expect(queryKeys.disclaimer()).toEqual(["disclaimer"]);
    expect(queryKeys.licenses()).toEqual(["licenses"]);
  });
});
