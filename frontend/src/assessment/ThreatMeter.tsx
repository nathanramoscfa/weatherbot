// frontend/src/assessment/ThreatMeter.tsx
import { clampThreatLevel } from "../app/ThreatLevelBadge.tsx";
import { cx, threatClasses } from "../ui/threat.ts";
import {
  FALLBACK_LEVELS,
  levelLabel,
  type LadderResponse,
} from "./vocabulary.ts";

export interface ThreatMeterProps {
  readonly level: number;
  readonly complete?: boolean;
  readonly ladder?: LadderResponse;
}

export function ThreatMeter({
  level,
  complete = true,
  ladder,
}: ThreatMeterProps) {
  const activeLevel = clampThreatLevel(level);
  const steps = ladder?.levels ?? FALLBACK_LEVELS;

  return (
    <ol
      aria-label="Threat level meter"
      data-testid="threat-meter"
      className="grid grid-cols-1 gap-1.5 sm:grid-cols-5"
    >
      {steps.map((step) => {
        const stepNumber = clampThreatLevel(step.number);
        const isCurrent = stepNumber === activeLevel;
        const palette = threatClasses(stepNumber);
        const label = step.label || levelLabel(stepNumber, ladder);

        return (
          <li
            key={stepNumber}
            aria-current={isCurrent ? "step" : undefined}
            data-testid={`threat-meter-step-${String(stepNumber)}`}
            className={cx(
              "flex items-center justify-between gap-1.5 rounded-control border px-2.5 py-1.5 sm:flex-col sm:items-start sm:justify-start sm:gap-0.5",
              isCurrent
                ? cx(
                    palette.solid,
                    "font-bold shadow-card ring-2 ring-brand/40",
                  )
                : palette.tint,
            )}
          >
            {isCurrent && (
              <span className="sr-only">
                {complete
                  ? `Level ${String(activeLevel)} of 5: `
                  : `At least Level ${String(activeLevel)} of 5: `}
              </span>
            )}
            <span
              className={cx(
                "text-caption tabular-nums leading-snug",
                isCurrent ? "font-bold" : "font-medium",
              )}
            >
              {String(stepNumber)}. {label}
            </span>
            {isCurrent && !complete && (
              <span
                data-testid="threat-meter-at-least"
                className="text-caption font-semibold leading-snug"
              >
                At least
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
