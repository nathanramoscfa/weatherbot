// frontend/src/app/navStatus.ts
import { useQuery } from "@tanstack/react-query";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { fetchAiStatus } from "../ai/queries.ts";
import { clampThreatLevel, type ThreatLevelNumber } from "./ThreatLevelBadge.tsx";

type AssessmentsResponse = components["schemas"]["AssessmentsResponse"];
type StormsResponse = components["schemas"]["StormsResponse"];
type AlertsResponse = components["schemas"]["AlertsResponse"];
type HealthResponse = components["schemas"]["HealthResponse"];
type AiStatusResponse = components["schemas"]["AiStatusResponse"];

export type NavBadgeTone = "level" | "count" | "ai" | "warning";

// One live status mark beside a navigation link. The mark is aria-hidden; the
// link's aria-describedby reads `description` in its place, so every link's
// text and accessible name stay its label.
export interface NavBadge {
  readonly tone: NavBadgeTone;
  readonly text: string;
  readonly description: string;
  readonly level?: ThreatLevelNumber;
}

export type NavBadges = Readonly<Partial<Record<string, NavBadge>>>;

async function fetchAssessments(): Promise<AssessmentsResponse> {
  const { data, response } = await apiClient.GET("/api/assessments");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/assessments", response.status);
  }
  return data;
}

async function fetchStorms(): Promise<StormsResponse> {
  const { data, response } = await apiClient.GET("/api/storms");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/storms", response.status);
  }
  return data;
}

async function fetchAlerts(): Promise<AlertsResponse> {
  const { data, response } = await apiClient.GET("/api/alerts");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/alerts", response.status);
  }
  return data;
}

function aiStateWords(state: string): string {
  switch (state) {
    case "paused":
      return "Paused";
    case "capped":
      return "Capped";
    case "off":
      return "Off";
    case "unavailable":
      return "Unavailable";
    default:
      return state;
  }
}

function plural(count: number, one: string, many: string): string {
  return `${String(count)} ${count === 1 ? one : many}`;
}

// Pure: the badges for a set of query answers (tested without a server).
export function deriveNavBadges(input: {
  readonly assessments?: AssessmentsResponse | undefined;
  readonly storms?: StormsResponse | undefined;
  readonly alerts?: AlertsResponse | undefined;
  readonly ai?: AiStatusResponse | undefined;
  readonly health?: HealthResponse | undefined;
}): NavBadges {
  const badges: Record<string, NavBadge> = {};

  const assessed = (input.assessments?.locations ?? []).flatMap((item) =>
    item.assessment ? [item.assessment] : [],
  );
  if (assessed.length > 0) {
    const highest = assessed.reduce((top, item) =>
      item.level.number > top.level.number ? item : top,
    );
    const level = clampThreatLevel(highest.level.number);
    badges["/"] = {
      tone: "level",
      level,
      text: String(level),
      description: `Highest current level: ${String(level)}, ${highest.level.label}`,
    };
  }

  const stormCount = input.storms?.storms.length ?? 0;
  if (stormCount > 0) {
    badges["/storms"] = {
      tone: "count",
      text: String(stormCount),
      description: `${plural(stormCount, "active storm", "active storms")}`,
    };
  }

  const covering = new Set<string>();
  for (const location of input.alerts?.locations ?? []) {
    for (const alert of location.alerts ?? []) {
      if (alert.covers) {
        covering.add(alert.id);
      }
    }
  }
  if (covering.size > 0) {
    badges["/alerts"] = {
      tone: "count",
      text: String(covering.size),
      description: `${plural(covering.size, "alert covers", "alerts cover")} a watched location`,
    };
  }

  const aiState = input.ai?.state ?? input.health?.ai.state;
  if (aiState !== undefined && aiState !== "ready") {
    const words = aiStateWords(aiState);
    badges["/ask"] = {
      tone: "ai",
      text: words,
      description: `AI is ${words.toLowerCase()}`,
    };
  }

  if (input.health?.stale) {
    badges["/settings"] = {
      tone: "warning",
      text: "!",
      description: "The monitor's data is stale",
    };
  }

  return badges;
}

// The navigation's live badges, read from the routes the pages already query,
// through the same shared keys, so a page and the shell share one cache entry
// and the server's events refresh both. Nothing here polls.
//
// The AI state is observed passively (`enabled: false`): the shell never asks
// for /api/ai itself, so a page that makes no AI request (/replay) still makes
// none, but every answer an AI page fetches or an `ai` event refreshes shows
// here. /api/health carries the same state, computed without a request, and
// whichever of the two answered last is the one shown.
export function useNavBadges(
  health: HealthResponse | undefined,
  healthUpdatedAt = 0,
): NavBadges {
  const assessments = useQuery({
    queryKey: queryKeys.assessments(),
    queryFn: fetchAssessments,
  });
  const storms = useQuery({ queryKey: queryKeys.storms(), queryFn: fetchStorms });
  const alerts = useQuery({ queryKey: queryKeys.alerts(), queryFn: fetchAlerts });
  const ai = useQuery({
    queryKey: queryKeys.ai(),
    queryFn: fetchAiStatus,
    enabled: false,
  });
  const aiIsNewer = ai.data !== undefined && ai.dataUpdatedAt >= healthUpdatedAt;
  return deriveNavBadges({
    assessments: assessments.data,
    storms: storms.data,
    alerts: alerts.data,
    ai: aiIsNewer ? ai.data : undefined,
    health,
  });
}
