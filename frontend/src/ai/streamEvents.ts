// frontend/src/ai/streamEvents.ts
import type { components } from "../api/schema.ts";

export type BriefingStreamEvent = components["schemas"]["BriefingStreamEvent"];
export type ChatStreamEvent = components["schemas"]["ChatStreamEvent"];
export type NarrationStreamEvent =
  components["schemas"]["NarrationStreamEvent"];
export type SectionName = components["schemas"]["SectionName"];
export type ChatTool = NonNullable<ChatStreamEvent["tool"]>;

type FieldKind = "string" | "number" | "boolean" | "array";

const SECTION_NAMES: Readonly<Record<SectionName, true>> = {
  situation: true,
  what_it_means_here: true,
  timeline: true,
  actions: true,
  sources: true,
};

const CHAT_TOOLS: Readonly<Record<ChatTool, true>> = {
  list_locations: true,
  get_assessment: true,
  get_evidence: true,
  get_alerts: true,
  get_storms: true,
  get_storm: true,
  get_outlook: true,
  get_ladder: true,
  get_history: true,
  unknown_tool: true,
};

const BRIEFING_KINDS: Readonly<Record<BriefingStreamEvent["kind"], true>> = {
  started: true,
  section: true,
  done: true,
  withheld: true,
  unavailable: true,
};

const CHAT_KINDS: Readonly<Record<ChatStreamEvent["kind"], true>> = {
  started: true,
  tool: true,
  text: true,
  done: true,
  withheld: true,
  unavailable: true,
};

const NARRATION_KINDS: Readonly<Record<NarrationStreamEvent["kind"], true>> = {
  started: true,
  done: true,
  withheld: true,
  unavailable: true,
};

const BRIEFING_FIELDS: Readonly<Record<string, FieldKind>> = {
  model: "string",
  model_name: "string",
  assessment_id: "number",
  as_of: "string",
  prompt_version: "string",
  section: "string",
  text: "string",
  output_id: "number",
  created_at: "string",
  reused: "boolean",
  reason: "string",
  detail: "string",
};

const CHAT_FIELDS: Readonly<Record<string, FieldKind>> = {
  conversation_id: "string",
  model: "string",
  model_name: "string",
  tool: "string",
  text: "string",
  call_ids: "array",
  reason: "string",
  detail: "string",
};

const NARRATION_FIELDS: Readonly<Record<string, FieldKind>> = {
  model: "string",
  model_name: "string",
  basin: "string",
  horizon: "string",
  graphic_sha256: "string",
  two_issued_at: "string",
  prompt_version: "string",
  output_id: "number",
  created_at: "string",
  reused: "boolean",
  summary: "string",
  areas: "array",
  caveat: "string",
  reason: "string",
  detail: "string",
};

function fieldsOf(value: unknown): Map<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return new Map(Object.entries(value));
}

function matches(value: unknown, kind: FieldKind): boolean {
  if (value === null || value === undefined) {
    return true;
  }
  if (kind === "array") {
    return Array.isArray(value);
  }
  return typeof value === kind;
}

function hasFields(
  fields: Map<string, unknown>,
  expected: Readonly<Record<string, FieldKind>>,
): boolean {
  return Object.entries(expected).every(([name, kind]) =>
    matches(fields.get(name), kind),
  );
}

function hasKind(
  fields: Map<string, unknown>,
  kinds: Readonly<Record<string, true>>,
): boolean {
  const kind = fields.get("kind");
  return typeof kind === "string" && Object.hasOwn(kinds, kind);
}

function isOneOf(
  value: unknown,
  allowed: Readonly<Record<string, true>>,
): boolean {
  return (
    value === null ||
    value === undefined ||
    (typeof value === "string" && Object.hasOwn(allowed, value))
  );
}

function isArea(value: unknown): boolean {
  const fields = fieldsOf(value);
  return (
    fields !== null &&
    typeof fields.get("description") === "string" &&
    typeof fields.get("chance_text") === "string"
  );
}

export function isBriefingStreamEvent(
  value: unknown,
): value is BriefingStreamEvent {
  const fields = fieldsOf(value);
  return (
    fields !== null &&
    hasKind(fields, BRIEFING_KINDS) &&
    hasFields(fields, BRIEFING_FIELDS) &&
    isOneOf(fields.get("section"), SECTION_NAMES)
  );
}

export function isChatStreamEvent(value: unknown): value is ChatStreamEvent {
  const fields = fieldsOf(value);
  if (
    fields === null ||
    !hasKind(fields, CHAT_KINDS) ||
    !hasFields(fields, CHAT_FIELDS) ||
    !isOneOf(fields.get("tool"), CHAT_TOOLS)
  ) {
    return false;
  }
  const callIds = fields.get("call_ids");
  return (
    !Array.isArray(callIds) ||
    callIds.every((item) => typeof item === "number")
  );
}

export function isNarrationStreamEvent(
  value: unknown,
): value is NarrationStreamEvent {
  const fields = fieldsOf(value);
  if (
    fields === null ||
    !hasKind(fields, NARRATION_KINDS) ||
    !hasFields(fields, NARRATION_FIELDS)
  ) {
    return false;
  }
  const areas = fields.get("areas");
  return !Array.isArray(areas) || areas.every(isArea);
}
