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
    <div className="mt-2 border-t border-slate-200 pt-2 dark:border-slate-700">
      <p className="font-semibold text-slate-800 dark:text-slate-200">
        Deciding evidence
      </p>
      <ul className="mt-1 space-y-1 text-slate-700 dark:text-slate-300">
        {evidence.map((ev, idx) => (
          <li key={`${ev.product}-${String(idx)}`}>
            <span>{ev.detail}</span>
            {ev.code ? ` · ${ev.code}` : ""}
            {ev.source_id ? ` (${ev.source_id})` : ""}
            {ev.distance_km !== null && ev.distance_km !== undefined
              ? ` · ${formatKm(ev.distance_km)}${ev.at_end ? " (at its end)" : ""}`
              : ""}
            {ev.issued_at
              ? ` · issued ${formatBothTimes(ev.issued_at, timeZone)}`
              : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
