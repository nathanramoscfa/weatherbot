// frontend/src/assessment/WhyThisLevel.tsx
import type { ReactNode } from "react";
import type { components } from "../api/schema.ts";
import { formatBothTimes, formatBreakpointSpan } from "../pages/format.ts";
import { Disclosure } from "../ui/Disclosure.tsx";
import { EvidenceList } from "./EvidenceList.tsx";
import { LevelSummary, UnavailableBanner } from "./LevelSummary.tsx";
import { OfficialProductList } from "./OfficialProductList.tsx";
import { ThreatTable } from "./ThreatTable.tsx";

type BreakpointSpan = components["schemas"]["BreakpointSpan"];
type ThreatLevelResponse = components["schemas"]["ThreatLevelResponse"];
type AssessmentEvidenceResponse =
  components["schemas"]["AssessmentEvidenceResponse"];
type AssessmentOfficialProductResponse =
  components["schemas"]["AssessmentOfficialProductResponse"];
type WindReadingResponse = components["schemas"]["WindReadingResponse"];
type StormThreatResponse = components["schemas"]["StormThreatResponse"];
type AssessmentUnavailableResponse =
  components["schemas"]["AssessmentUnavailableResponse"];

export interface WhyThisLevelAssessment {
  readonly snapshot_id: string;
  readonly as_of: string;
  readonly stored_at?: string;
  readonly level: ThreatLevelResponse;
  readonly rule: string;
  readonly rule_trigger: string;
  readonly complete: boolean;
  readonly unavailable: readonly AssessmentUnavailableResponse[];
  readonly evidence: readonly AssessmentEvidenceResponse[];
  readonly official: readonly AssessmentOfficialProductResponse[];
  readonly wind_probabilities: readonly WindReadingResponse[];
  readonly threats: readonly StormThreatResponse[];
  readonly breakpoint_span: BreakpointSpan | null;
  readonly ruleset: string;
}

export interface WhyThisLevelProps {
  readonly assessment: WhyThisLevelAssessment;
  readonly insideNwsCoverage: boolean;
  readonly timeZone?: string | null;
  readonly breakpointSpan?: BreakpointSpan | null;
  readonly zones?: readonly string[];
  readonly controls?: ReactNode;
  readonly children?: ReactNode;
}

export function WhyThisLevel({
  assessment,
  insideNwsCoverage,
  timeZone = null,
  breakpointSpan,
  zones,
  controls,
  children,
}: WhyThisLevelProps) {
  const effectiveSpan =
    breakpointSpan !== undefined ? breakpointSpan : assessment.breakpoint_span;

  const derivedZones =
    zones !== undefined && zones.length > 0
      ? zones
      : Array.from(
          new Set(assessment.official.flatMap((prod) => prod.zones)),
        );

  const defaultChildren = (
    <>
      <LevelSummary assessment={assessment}>
        <EvidenceList evidence={assessment.evidence} timeZone={timeZone} />
      </LevelSummary>
      <OfficialProductList
        official={assessment.official}
        timeZone={timeZone}
      />
      <ThreatTable
        threats={assessment.threats}
        windProbabilities={assessment.wind_probabilities}
        asOf={assessment.as_of}
        timeZone={timeZone}
      />
    </>
  );

  return (
    <Disclosure
      summary="Why this level / Official provenance & controls"
      data-testid="why-this-level"
    >
      {children ?? defaultChildren}

      <UnavailableBanner
        complete={assessment.complete}
        unavailable={assessment.unavailable}
      />

      <div
        data-testid="provenance-coverage"
        className="rounded-md border border-line bg-surface-inset p-3 text-sm"
      >
        <p className="font-semibold text-ink">Coverage &amp; zones</p>
        <p className="mt-1 text-ink-muted">
          {insideNwsCoverage ? "Inside NWS coverage" : "Outside NWS coverage"} ·
          Time zone: <span className="font-mono">{timeZone ?? "UTC"}</span> ·
          Breakpoint span: {formatBreakpointSpan(effectiveSpan)}
          {derivedZones.length > 0
            ? ` · Zones: ${derivedZones.join(", ")}`
            : ""}
        </p>
      </div>

      <div
        data-testid="provenance-snapshot"
        className="rounded-md border border-line bg-surface-inset p-3 text-sm tabular-nums"
      >
        <p className="font-semibold text-ink">Assessment &amp; snapshot</p>
        <p className="mt-1 text-ink-muted">
          Assessed instant: {formatBothTimes(assessment.as_of, timeZone)}
          {assessment.stored_at
            ? ` · Stored: ${formatBothTimes(assessment.stored_at, timeZone)}`
            : ""}
        </p>
        <span className="mt-1 block text-caption text-ink-subtle">
          Snapshot ID:{" "}
          <code className="font-mono text-ink">{assessment.snapshot_id}</code> ·
          Ruleset:{" "}
          <code className="font-mono text-ink">
            {assessment.ruleset.slice(0, 12)}
          </code>
        </span>
      </div>

      {controls !== undefined && controls !== null && (
        <div data-testid="provenance-controls">{controls}</div>
      )}
    </Disclosure>
  );
}
