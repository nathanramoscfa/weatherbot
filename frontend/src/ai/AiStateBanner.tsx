// frontend/src/ai/AiStateBanner.tsx
import { CirclePause, PowerOff, TriangleAlert } from "lucide-react";
import { formatUsd } from "./format.ts";
import {
  type AiStateName,
  type AiUnavailableReason,
  reasonText,
} from "./reasons.ts";

export const AI_OFF_NO_CREDENTIAL =
  "AI is off: no Anthropic credential. Set ANTHROPIC_API_KEY or run ant auth login, then restart serve.";
export const AI_OFF_DISABLED =
  "AI is off: [ai] enabled is false in weatherbot.toml.";
export const AI_PAUSED = "AI paused by you — resume it in Settings.";
export const AI_AUTH_FAILED =
  "AI unavailable: authentication failed — check the credential, then restart serve.";
export const AI_BUSY =
  "AI busy: four AI requests are running already. Try again in a moment.";

export function aiStateMessage(
  state: AiStateName,
  reason: AiUnavailableReason | null,
  capMicroUsd?: number | null,
): string | null {
  switch (state) {
    case "ready":
      return null;
    case "off":
      return reason === "disabled" ? AI_OFF_DISABLED : AI_OFF_NO_CREDENTIAL;
    case "paused":
      return AI_PAUSED;
    case "capped": {
      const cap =
        capMicroUsd === null || capMicroUsd === undefined
          ? ""
          : ` ${formatUsd(capMicroUsd)}`;
      return `AI paused: today's${cap} cap is reached. It resets at midnight; you can allow more in Settings.`;
    }
    case "unavailable":
      if (reason === "auth_failed") {
        return AI_AUTH_FAILED;
      }
      if (reason === "busy") {
        return AI_BUSY;
      }
      return `AI unavailable: ${reason === null ? "the reason is unknown" : reasonText(reason)}.`;
  }
}

export interface AiStateBannerProps {
  readonly state: AiStateName;
  readonly reason: AiUnavailableReason | null;
  readonly capMicroUsd?: number | null;
}

export function AiStateBanner({
  state,
  reason,
  capMicroUsd,
}: AiStateBannerProps) {
  const message = aiStateMessage(state, reason, capMicroUsd);
  if (message === null) {
    return null;
  }
  const Icon =
    state === "off" ? PowerOff : state === "unavailable" ? TriangleAlert : CirclePause;
  return (
    <div
      role="status"
      data-testid="ai-state-banner"
      className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-700/80 dark:bg-amber-950/60 dark:text-amber-100"
    >
      <Icon
        className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-700 dark:text-amber-400"
        aria-hidden="true"
      />
      <span>{message}</span>
    </div>
  );
}
