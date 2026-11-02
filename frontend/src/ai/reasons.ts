// frontend/src/ai/reasons.ts
import type { components } from "../api/schema.ts";

export type AiStateName = components["schemas"]["AiStateName"];
export type AiUnavailableReason = components["schemas"]["AiUnavailableReason"];

const AI_REASONS: Readonly<Record<AiUnavailableReason, true>> = {
  disabled: true,
  no_credential: true,
  price_unknown: true,
  paused: true,
  capped: true,
  busy: true,
  auth_failed: true,
  permission: true,
  not_found: true,
  rate_limited: true,
  overloaded: true,
  server_error: true,
  timeout: true,
  network: true,
  bad_request: true,
  too_large: true,
  declined: true,
  truncated: true,
};

const AI_REASON_SET: ReadonlySet<string> = new Set(Object.keys(AI_REASONS));

export function isAiUnavailableReason(
  value: unknown,
): value is AiUnavailableReason {
  return typeof value === "string" && AI_REASON_SET.has(value);
}

export function reasonText(reason: AiUnavailableReason): string {
  switch (reason) {
    case "disabled":
      return "AI is turned off by [ai] enabled";
    case "no_credential":
      return "there is no Anthropic credential";
    case "price_unknown":
      return "the model is not in the price table, so the cap cannot price it";
    case "paused":
      return "AI is paused";
    case "capped":
      return "today's AI cap is reached";
    case "busy":
      return "too many AI requests are running";
    case "auth_failed":
      return "Anthropic refused the credential (authentication failed)";
    case "permission":
      return "the credential is not allowed to use this model";
    case "not_found":
      return "Anthropic does not know the model";
    case "rate_limited":
      return "Anthropic is rate-limiting this credential";
    case "overloaded":
      return "Anthropic is overloaded or temporarily unavailable";
    case "server_error":
      return "Anthropic answered with a server error";
    case "timeout":
      return "the request to Anthropic timed out";
    case "network":
      return "Anthropic could not be reached";
    case "bad_request":
      return "Anthropic refused the request as malformed";
    case "too_large":
      return "the request is too large";
    case "declined":
      return "the model declined to answer";
    case "truncated":
      return "the answer was cut off at its token limit";
  }
}

export function stateForReason(reason: AiUnavailableReason): AiStateName {
  switch (reason) {
    case "disabled":
    case "no_credential":
      return "off";
    case "paused":
      return "paused";
    case "capped":
      return "capped";
    default:
      return "unavailable";
  }
}

export function withheldText(reason: string | null): string {
  switch (reason) {
    case "level":
      return "it stated a level other than the engine's";
    case "source":
      return "it cited a source its context did not hold";
    case "url":
      return "it carried a URL";
    case "coordinate":
      return "it carried a position not quoted from an official product";
    case "empty":
      return "a required section was empty";
    case "length":
      return "a section passed its length bound";
    case "chance":
      return "it stated a chance the outlook does not";
    case "incomplete":
      return "it did not arrive whole";
    case "invalid_output":
      return "the answer did not match its schema";
    case null:
      return "a validator refused it";
    default:
      return reason;
  }
}
