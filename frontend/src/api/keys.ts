// frontend/src/api/keys.ts
import type { components } from "./schema.ts";

export type InvalidatableQueryKey = components["schemas"]["QueryKey"];

export const INVALIDATABLE_QUERY_KEYS = [
  "health",
  "locations",
  "assessments",
  "storms",
  "alerts",
  "map",
  "timeline",
  "notifications",
  "settings",
  "ai",
  "briefings",
] as const satisfies readonly InvalidatableQueryKey[];

type MissingInvalidatableKey = Exclude<
  InvalidatableQueryKey,
  (typeof INVALIDATABLE_QUERY_KEYS)[number]
>;
const _exhaustiveInvalidatableKeys: MissingInvalidatableKey extends never
  ? true
  : never = true;
void _exhaustiveInvalidatableKeys;

export const STATIC_QUERY_KEYS = [
  "replay",
  "disclaimer",
  "licenses",
] as const;

export type StaticQueryKey = (typeof STATIC_QUERY_KEYS)[number];

const INVALIDATABLE_KEY_SET: ReadonlySet<string> = new Set<string>(
  INVALIDATABLE_QUERY_KEYS,
);

export function isInvalidatableQueryKey(
  value: string,
): value is InvalidatableQueryKey {
  return INVALIDATABLE_KEY_SET.has(value);
}

export function invalidatableQueryKey<K extends InvalidatableQueryKey>(
  key: K,
): readonly [K];
export function invalidatableQueryKey<
  K extends InvalidatableQueryKey,
  const P extends readonly unknown[],
>(key: K, ...params: P): readonly [K, ...P];
export function invalidatableQueryKey(
  key: InvalidatableQueryKey,
  ...params: readonly unknown[]
): readonly [InvalidatableQueryKey, ...unknown[]] {
  return [key, ...params];
}

export function staticQueryKey<K extends StaticQueryKey>(
  key: K,
): readonly [K];
export function staticQueryKey<
  K extends StaticQueryKey,
  const P extends readonly unknown[],
>(key: K, ...params: P): readonly [K, ...P];
export function staticQueryKey(
  key: StaticQueryKey,
  ...params: readonly unknown[]
): readonly [StaticQueryKey, ...unknown[]] {
  return [key, ...params];
}

export const queryKeys = {
  health: () => invalidatableQueryKey("health"),
  locations: () => invalidatableQueryKey("locations"),
  assessments: () => invalidatableQueryKey("assessments"),
  storms: () => invalidatableQueryKey("storms"),
  alerts: () => invalidatableQueryKey("alerts"),
  map: () => invalidatableQueryKey("map"),
  mapSnapshot: (snapshotId: string) =>
    invalidatableQueryKey("map", "snapshot", snapshotId),
  mapAdvisories: () => invalidatableQueryKey("map", "advisories"),
  mapDepth: (snapshotId: string | null) =>
    invalidatableQueryKey("map", "depth", snapshotId ?? "latest"),
  mapWindProbabilities: (scopeKey: string, thresholdKt: 34 | 50 | 64) =>
    invalidatableQueryKey("map", "wind-probabilities", scopeKey, thresholdKt),
  timeline: (location?: string) =>
    location !== undefined
      ? invalidatableQueryKey("timeline", location)
      : invalidatableQueryKey("timeline"),
  notifications: () => invalidatableQueryKey("notifications"),
  notificationChannels: () =>
    invalidatableQueryKey("notifications", "channels"),
  settings: () => invalidatableQueryKey("settings"),
  retention: (days?: number) =>
    days !== undefined
      ? invalidatableQueryKey("settings", "retention", days)
      : invalidatableQueryKey("settings", "retention"),
  ai: () => invalidatableQueryKey("ai"),
  aiCalls: () => invalidatableQueryKey("ai", "calls"),
  briefings: () => invalidatableQueryKey("briefings"),
  aiSummaries: () => invalidatableQueryKey("briefings", "summaries"),
  aiNarrations: (snapshotId: string | null) =>
    invalidatableQueryKey("briefings", "narrations", snapshotId),
  outlook: () => invalidatableQueryKey("storms", "outlook"),
  replay: () => staticQueryKey("replay"),
  replayAdvisory: (atcfId: string, advisory: string) =>
    staticQueryKey("replay", atcfId, advisory),
  disclaimer: () => staticQueryKey("disclaimer"),
  licenses: () => staticQueryKey("licenses"),
} as const;
