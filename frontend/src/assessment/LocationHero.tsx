// frontend/src/assessment/LocationHero.tsx
import type { components } from "../api/schema.ts";
import { clampThreatLevel } from "../app/ThreatLevelBadge.tsx";
import { formatAgeSeconds, formatFriendlyLocal } from "../pages/format.ts";
import { Callout } from "../ui/Callout.tsx";
import { cx, threatClasses } from "../ui/threat.ts";
import { ThreatMeter } from "./ThreatMeter.tsx";
import {
  levelActions,
  levelLabel,
  ruleSentence,
  type LadderResponse,
} from "./vocabulary.ts";

type ThreatLevelResponse = components["schemas"]["ThreatLevelResponse"];
type AssessmentUnavailableResponse =
  components["schemas"]["AssessmentUnavailableResponse"];

export interface LocationHeroAssessment {
  readonly as_of: string;
  readonly level: ThreatLevelResponse;
  readonly rule: string;
  readonly rule_trigger: string;
  readonly complete: boolean;
  readonly unavailable: readonly AssessmentUnavailableResponse[];
  readonly toggle_changed?: boolean;
  readonly toggle_note?: string | null;
}

export interface LocationHeroProps {
  readonly assessment: LocationHeroAssessment;
  readonly timeZone?: string | null;
  readonly ageSeconds?: number | null;
  readonly evacuationOrderOn?: boolean;
  readonly origin?: "live" | "replay";
  readonly ladder?: LadderResponse;
}

export function LocationHero({
  assessment,
  timeZone = null,
  ageSeconds = null,
  evacuationOrderOn = false,
  origin = "live",
  ladder,
}: LocationHeroProps) {
  const levelNumber = clampThreatLevel(assessment.level.number);
  const engineName =
    levelLabel(levelNumber, ladder) || assessment.level.label;
  const headline = assessment.complete
    ? `Level ${String(levelNumber)} — ${engineName}`
    : `At least Level ${String(levelNumber)} — ${engineName}`;
  const sentence =
    assessment.rule_trigger || ruleSentence(assessment.rule, ladder);
  const actions =
    assessment.level.actions || levelActions(levelNumber, ladder);
  const localTime = formatFriendlyLocal(assessment.as_of, timeZone);
  const ageText = formatAgeSeconds(ageSeconds ?? 0);
  const assessedCaption =
    origin === "replay"
      ? ageSeconds !== null
        ? `Historical advisory (${ageText})${localTime ? ` · ${localTime}` : ""}`
        : `Historical advisory${localTime ? ` · ${localTime}` : ""}`
      : `Assessed ${ageText}${localTime ? ` · ${localTime}` : ""}`;
  const palette = threatClasses(levelNumber);

  return (
    <div
      data-testid="location-hero"
      className="space-y-3"
    >
      <div
        className={cx(
          "rounded-card border p-4",
          palette.tint,
        )}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3
            data-testid="location-hero-headline"
            className="text-lg font-bold sm:text-xl"
          >
            {headline}
          </h3>
          <span
            data-testid="location-hero-assessed"
            className="text-caption tabular-nums font-medium"
          >
            {assessedCaption}
          </span>
        </div>

        <p
          data-testid="location-hero-sentence"
          className="mt-1.5 text-base font-medium"
        >
          {sentence}
        </p>

        <p
          data-testid="location-hero-actions"
          className="mt-2 text-sm"
        >
          <span className="font-semibold">Recommended actions:</span>{" "}
          {actions}
        </p>

        <div className="mt-3">
          <ThreatMeter
            level={levelNumber}
            complete={assessment.complete}
            {...(ladder !== undefined ? { ladder } : {})}
          />
        </div>
      </div>

      {!assessment.complete && (
        <Callout
          tone="warning"
          role="note"
          data-testid="location-hero-incomplete-callout"
          title="At least — incomplete assessment floor"
        >
          <p>
            One or more official inputs were unavailable when this assessment
            was computed, so {headline} is a minimum floor. Open the provenance
            disclosure below for the missing inputs.
          </p>
        </Callout>
      )}

      {assessment.toggle_changed && assessment.toggle_note && (
        <Callout
          tone="warning"
          role="note"
          data-testid="location-hero-toggle-callout"
        >
          <p>{assessment.toggle_note}</p>
        </Callout>
      )}

      {evacuationOrderOn && (
        <Callout
          tone="warning"
          role="note"
          data-testid="location-hero-evacuation-callout"
          title="Evacuation order is on"
        >
          <p>
            The manual evacuation-order override is active for this location,
            holding it at Level 4 ({levelLabel(4, ladder)}) or above.
          </p>
        </Callout>
      )}

      {origin === "replay" && (
        <Callout
          tone="note"
          role="note"
          data-testid="location-hero-replay-callout"
        >
          <p>
            Historical replay: the manual evacuation-order toggle is off for a
            past storm.
          </p>
        </Callout>
      )}
    </div>
  );
}
