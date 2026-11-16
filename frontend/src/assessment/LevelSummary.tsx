// frontend/src/assessment/LevelSummary.tsx
import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import type { components } from "../api/schema.ts";

type ThreatLevelResponse = components["schemas"]["ThreatLevelResponse"];
type AssessmentUnavailableResponse =
  components["schemas"]["AssessmentUnavailableResponse"];

export interface AssessmentSummaryData {
  readonly level: ThreatLevelResponse;
  readonly rule: string;
  readonly rule_trigger: string;
  readonly complete: boolean;
  readonly unavailable: readonly AssessmentUnavailableResponse[];
}

export interface UnavailableBannerProps {
  readonly complete: boolean;
  readonly unavailable: readonly AssessmentUnavailableResponse[];
}

export function UnavailableBanner({
  complete,
  unavailable,
}: UnavailableBannerProps) {
  if (complete) {
    return null;
  }

  return (
    <div
      role="note"
      className="rounded-md border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-600 dark:bg-amber-950/60 dark:text-amber-100"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400"
          aria-hidden="true"
        />
        <div className="space-y-1">
          <p className="font-semibold">
            At least: the level is a floor because these inputs were
            unavailable:
          </p>
          <ul className="list-disc space-y-0.5 pl-4">
            {unavailable.map((unavail, idx) => (
              <li key={`${unavail.kind}-${String(idx)}`}>
                <span className="font-medium">{unavail.kind}</span>
                {unavail.source_id ? ` (${unavail.source_id})` : ""}
                {unavail.storm_name ? ` — ${unavail.storm_name}` : ""}
                {unavail.threshold_kt !== null &&
                unavail.threshold_kt !== undefined
                  ? ` — ${String(unavail.threshold_kt)} kt`
                  : ""}
                : {unavail.reason}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export interface LevelSummaryProps {
  readonly assessment: AssessmentSummaryData;
  readonly children?: ReactNode;
}

export function LevelSummary({ assessment, children }: LevelSummaryProps) {
  return (
    <div className="rounded-md border border-line bg-surface-inset p-3 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-semibold text-ink">
          {assessment.rule_trigger}
        </p>
        <span className="text-caption text-ink-subtle">
          Rule ID:{" "}
          <code className="rounded bg-surface-card px-1.5 py-0.5 font-mono text-ink">
            {assessment.rule}
          </code>
        </span>
      </div>
      <p className="mt-1.5 text-ink-muted">
        Recommended actions: {assessment.level.actions}
      </p>
      {children}
    </div>
  );
}
