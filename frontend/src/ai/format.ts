// frontend/src/ai/format.ts
import type { components } from "../api/schema.ts";
import type { ChatTool } from "./streamEvents.ts";

type Basin = components["schemas"]["Basin"];
type Horizon = components["schemas"]["Horizon"];
type CredentialSource = components["schemas"]["CredentialSource"];

const MICRO_PER_USD = 1_000_000;
const FAMILY = /^[a-z]+$/;
const NUMBER = /^\d+$/;

export function modelDisplayName(
  model: string,
  modelName?: string | null,
): string {
  if (modelName && modelName !== model) {
    return modelName;
  }
  const [vendor, family = "", ...version] = model.split("-");
  if (
    vendor !== "claude" ||
    !FAMILY.test(family) ||
    version.length < 1 ||
    version.length > 2 ||
    !version.every((part) => NUMBER.test(part))
  ) {
    return model;
  }
  return `Claude ${family.charAt(0).toUpperCase()}${family.slice(1)} ${version.join(".")}`;
}

export function browserTimeZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return undefined;
  }
}

export function formatUsd(microUsd: number): string {
  return `$${(microUsd / MICRO_PER_USD).toFixed(2)}`;
}

export function formatUsdPrecise(microUsd: number): string {
  return `$${(microUsd / MICRO_PER_USD).toFixed(4)}`;
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

export function basinName(basin: Basin): string {
  switch (basin) {
    case "atl":
      return "Atlantic";
    case "pac":
      return "Eastern Pacific";
    case "cpac":
      return "Central Pacific";
  }
}

export function horizonName(horizon: Horizon): string {
  switch (horizon) {
    case "2d0":
      return "two-day";
    case "7d0":
      return "seven-day";
  }
}

export function credentialSourceText(
  source: CredentialSource | null,
): string {
  switch (source) {
    case "environment":
      return "the ANTHROPIC_API_KEY environment variable";
    case "auth_token":
      return "the ANTHROPIC_AUTH_TOKEN environment variable";
    case "profile":
      return "an ant auth login profile";
    case "none":
      return "none found";
    case null:
      return "not read ([ai] enabled is false)";
  }
}

export function toolChipText(tool: ChatTool): string {
  switch (tool) {
    case "list_locations":
      return "Reading locations";
    case "get_assessment":
      return "Reading the assessment";
    case "get_evidence":
      return "Reading the evidence";
    case "get_alerts":
      return "Reading alerts";
    case "get_storms":
      return "Reading storms";
    case "get_storm":
      return "Reading a storm";
    case "get_outlook":
      return "Reading the outlook";
    case "get_ladder":
      return "Reading the ladder";
    case "get_history":
      return "Reading history";
    case "unknown_tool":
      return "Asked for an unknown lookup";
  }
}

export function isPublicHttpsUrl(url: string | null | undefined): url is string {
  if (!url) {
    return false;
  }
  try {
    return new URL(url).protocol === "https:";
  } catch {
    return false;
  }
}
