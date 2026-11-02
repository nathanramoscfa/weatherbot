// frontend/src/ai/queries.ts
import { ApiRequestError, apiClient } from "../api/client.ts";
import type { components } from "../api/schema.ts";

export type AiStatusResponse = components["schemas"]["AiStatusResponse"];
export type AiCallsResponse = components["schemas"]["AiCallsResponse"];
export type AiCallResponse = components["schemas"]["AiCallResponse"];
export type BriefingsResponse = components["schemas"]["BriefingsResponse"];
export type StoredBriefingResponse =
  components["schemas"]["StoredBriefingResponse"];
export type SummariesResponse = components["schemas"]["SummariesResponse"];
export type StoredSummaryResponse =
  components["schemas"]["StoredSummaryResponse"];
export type NarrationsResponse = components["schemas"]["NarrationsResponse"];
export type StoredNarrationResponse =
  components["schemas"]["StoredNarrationResponse"];
export type OutlookGraphicsResponse =
  components["schemas"]["OutlookGraphicsResponse"];
export type OutlookGraphicResponse =
  components["schemas"]["OutlookGraphicResponse"];
export type AiSourceResponse = components["schemas"]["AiSourceResponse"];

export async function fetchAiStatus(): Promise<AiStatusResponse> {
  const { data, response } = await apiClient.GET("/api/ai");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/ai", response.status);
  }
  return data;
}

export async function fetchAiCalls(): Promise<AiCallsResponse> {
  const { data, response } = await apiClient.GET("/api/ai/calls");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/ai/calls", response.status);
  }
  return data;
}

export async function fetchBriefings(): Promise<BriefingsResponse> {
  const { data, response } = await apiClient.GET("/api/ai/briefings");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/ai/briefings", response.status);
  }
  return data;
}

const SUMMARIES_LIMIT = 200;

export async function fetchSummaries(): Promise<SummariesResponse> {
  const { data, response } = await apiClient.GET("/api/ai/summaries", {
    params: { query: { limit: SUMMARIES_LIMIT } },
  });
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/ai/summaries", response.status);
  }
  return data;
}

export async function fetchNarrations(): Promise<NarrationsResponse> {
  const { data, response } = await apiClient.GET("/api/ai/narrations");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/ai/narrations", response.status);
  }
  return data;
}

export async function fetchOutlook(): Promise<OutlookGraphicsResponse> {
  const { data, response } = await apiClient.GET("/api/outlook");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/outlook", response.status);
  }
  return data;
}
