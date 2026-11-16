// frontend/src/dashboard/StatusBar.tsx
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import type { components } from "../api/schema.ts";
import {
  formatAgeSeconds,
  formatFriendlyLocal,
  formatUtc,
} from "../pages/format.ts";
import { buttonClasses } from "../ui/Button.tsx";
import { Callout } from "../ui/Callout.tsx";
import { Card } from "../ui/Card.tsx";
import { ExportPopover } from "./ExportPopover.tsx";

export type SnapshotStatusResponse = NonNullable<
  components["schemas"]["AssessmentsResponse"]["snapshot"]
>;

const DAY_MS = 24 * 60 * 60 * 1000;
const MINUTE_MS = 60_000;

export function resolveEffectiveNowMs(
  serverNow: string | null | undefined,
  mountedClientMs: number,
  currentClientMs: number,
): number {
  if (serverNow) {
    const parsedServerMs = Date.parse(serverNow);
    if (Number.isFinite(parsedServerMs)) {
      if (Math.abs(currentClientMs - parsedServerMs) > DAY_MS) {
        return parsedServerMs + Math.max(0, currentClientMs - mountedClientMs);
      }
    }
  }
  return currentClientMs;
}

export function computeCountdownMinutes(
  nextProductAt: string,
  effectiveNowMs: number,
): number | null {
  const targetMs = Date.parse(nextProductAt);
  if (!Number.isFinite(targetMs)) {
    return null;
  }
  const diffMs = targetMs - effectiveNowMs;
  return Math.max(0, Math.ceil(diffMs / MINUTE_MS));
}

export interface CycleStatusMessage {
  readonly kind: "info" | "error";
  readonly text: string;
}

export interface StatusBarProps {
  readonly snapshot: SnapshotStatusResponse | null;
  readonly nextProductAt: string | null;
  readonly serverNow?: string | null;
  readonly timeZone?: string | null;
  readonly hasAnyAssessment: boolean;
  readonly locationNames: readonly string[];
  readonly includeBriefing: boolean;
  readonly onIncludeBriefingChange: (nextChecked: boolean) => void;
  readonly cycleRunning: boolean;
  readonly onCheckNow: () => void;
  readonly cycleMessage: CycleStatusMessage | null;
  readonly evacError: string | null;
}

interface NextProductCountdownProps {
  readonly nextProductAt: string;
  readonly serverNow: string | null;
  readonly timeZone: string | null;
}

function NextProductCountdown({
  nextProductAt,
  serverNow,
  timeZone,
}: NextProductCountdownProps) {
  const [clock, setClock] = useState<{
    readonly mountedMs: number;
    readonly nowMs: number;
  }>(() => {
    const initial = Date.now();
    return { mountedMs: initial, nowMs: initial };
  });

  const effectiveNowMs = resolveEffectiveNowMs(
    serverNow,
    clock.mountedMs,
    clock.nowMs,
  );

  useEffect(() => {
    let timerId: ReturnType<typeof setTimeout> | null = null;

    const clearTimer = () => {
      if (timerId !== null) {
        clearTimeout(timerId);
        timerId = null;
      }
    };

    const scheduleNextMinute = () => {
      clearTimer();
      if (typeof document !== "undefined" && document.hidden) {
        return;
      }
      const currentClientMs = Date.now();
      const currentEffectiveMs = resolveEffectiveNowMs(
        serverNow,
        clock.mountedMs,
        currentClientMs,
      );
      const remainderMs = currentEffectiveMs % MINUTE_MS;
      const delayMs = remainderMs === 0 ? MINUTE_MS : MINUTE_MS - remainderMs;
      timerId = setTimeout(() => {
        if (typeof document !== "undefined" && document.hidden) {
          return;
        }
        setClock((prev) => ({ ...prev, nowMs: Date.now() }));
      }, delayMs);
    };

    scheduleNextMinute();

    const handleVisibilityChange = () => {
      if (typeof document !== "undefined" && document.hidden) {
        clearTimer();
      } else {
        setClock((prev) => ({ ...prev, nowMs: Date.now() }));
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      clearTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [nextProductAt, serverNow, clock.mountedMs, clock.nowMs]);

  const countdownMinutes = computeCountdownMinutes(
    nextProductAt,
    effectiveNowMs,
  );
  if (countdownMinutes === null) {
    return null;
  }
  const nextProductLocal = formatFriendlyLocal(nextProductAt, timeZone);

  return (
    <span
      data-testid="next-product-countdown"
      title={formatUtc(nextProductAt)}
      className="inline-flex flex-wrap items-baseline gap-1.5 lg:whitespace-nowrap"
    >
      <span>
        Next NHC product in{" "}
        <strong className="font-semibold text-ink">
          {String(countdownMinutes)} min
        </strong>
      </span>
      {nextProductLocal && (
        <time
          dateTime={nextProductAt}
          className="text-caption text-ink-subtle"
        >
          ({nextProductLocal})
        </time>
      )}
    </span>
  );
}

export function StatusBar({
  snapshot,
  nextProductAt,
  serverNow = null,
  timeZone = null,
  hasAnyAssessment,
  locationNames,
  includeBriefing,
  onIncludeBriefingChange,
  cycleRunning,
  onCheckNow,
  cycleMessage,
  evacError,
}: StatusBarProps) {
  return (
    <Card
      as="section"
      aria-label="Monitor cycle controls"
      padding="sm"
      data-testid="status-bar"
    >
      <div
        data-testid="status-bar-row"
        className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 lg:flex-nowrap"
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted tabular-nums lg:flex-nowrap">
          {snapshot ? (
            <span
              data-testid="status-bar-snapshot"
              title={`Completed ${formatUtc(snapshot.completed_at)}`}
              className="inline-flex flex-wrap items-baseline gap-1.5 lg:whitespace-nowrap"
            >
              <span>
                Snapshot:{" "}
                <strong className="font-semibold text-ink">
                  {snapshot.status}
                </strong>{" "}
                · {formatAgeSeconds(snapshot.age_seconds)}
              </span>
              <time
                dateTime={snapshot.completed_at}
                className="text-caption text-ink-subtle"
              >
                ({formatUtc(snapshot.completed_at)})
              </time>
            </span>
          ) : (
            <span
              data-testid="status-bar-snapshot"
              className="lg:whitespace-nowrap"
            >
              No snapshot stored yet.
            </span>
          )}

          {nextProductAt !== null && (
            <NextProductCountdown
              key={`${nextProductAt}-${serverNow ?? ""}`}
              nextProductAt={nextProductAt}
              serverNow={serverNow}
              timeZone={timeZone}
            />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 lg:shrink-0 lg:flex-nowrap">
          {hasAnyAssessment && (
            <ExportPopover
              locationNames={locationNames}
              includeBriefing={includeBriefing}
              onIncludeBriefingChange={onIncludeBriefingChange}
            />
          )}
          <button
            type="button"
            onClick={onCheckNow}
            disabled={cycleRunning}
            className={buttonClasses("primary", "sm", "lg:whitespace-nowrap")}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 shrink-0 ${cycleRunning ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            <span>Check now</span>
          </button>
        </div>
      </div>

      {cycleMessage && (
        <Callout
          tone={cycleMessage.kind === "error" ? "error" : "info"}
          role={cycleMessage.kind === "error" ? "alert" : "status"}
          className="mt-2.5"
        >
          <p>{cycleMessage.text}</p>
        </Callout>
      )}

      {evacError && (
        <Callout tone="error" role="alert" className="mt-2.5">
          <p>{evacError}</p>
        </Callout>
      )}
    </Card>
  );
}
