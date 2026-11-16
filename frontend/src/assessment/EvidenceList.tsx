// frontend/src/assessment/EvidenceList.tsx
import type { components } from "../api/schema.ts";
import { formatBothTimes, formatKm } from "../pages/format.ts";

type AssessmentEvidenceResponse =
  components["schemas"]["AssessmentEvidenceResponse"];

export interface EvidenceListProps {
  readonly evidence: readonly AssessmentEvidenceResponse[];
  readonly timeZone: string | null | undefined;
}

export function EvidenceList({ evidence, timeZone }: EvidenceListProps) {
  if (evidence.length === 0) {
    return null;
  }

  return (
    <div className="mt-2 border-t border-line pt-2">
      <p className="font-semibold text-ink">
        Deciding evidence
      </p>
      <ul className="mt-1.5 space-y-2 text-ink-muted tabular-nums">
        {evidence.map((ev, idx) => {
          const metaParts: string[] = [];
          if (ev.code) {
            metaParts.push(ev.code);
          }
          if (ev.source_id) {
            metaParts.push(`(${ev.source_id})`);
          }
          if (ev.distance_km !== null && ev.distance_km !== undefined) {
            metaParts.push(
              `${formatKm(ev.distance_km)}${ev.at_end ? " (at its end)" : ""}`,
            );
          }
          if (ev.issued_at) {
            metaParts.push(`issued ${formatBothTimes(ev.issued_at, timeZone)}`);
          }

          return (
            <li key={`${ev.product}-${String(idx)}`} className="max-w-measure">
              <span className="block text-sm text-ink">{ev.detail}</span>
              {metaParts.length > 0 && (
                <span className="mt-0.5 block text-caption text-ink-subtle tabular-nums">
                  {metaParts.join(" · ")}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
