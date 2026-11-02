// frontend/src/ai/ChangeSummary.tsx
import { AiLabel } from "./AiLabel.tsx";
import { AiSources, AiText } from "./AiText.tsx";
import type { StoredSummaryResponse } from "./queries.ts";
import { withheldText } from "./reasons.ts";

export interface ChangeSummaryProps {
  readonly summary: StoredSummaryResponse;
}

export function ChangeSummary({ summary }: ChangeSummaryProps) {
  return (
    <section
      aria-label={`AI summary of assessment ${String(summary.assessment_id ?? "?")}`}
      className="mt-2 space-y-1.5 rounded-md border border-violet-200 bg-violet-50/50 p-2.5 dark:border-violet-900/70 dark:bg-violet-950/20"
    >
      <AiLabel
        kind="AI summary of what changed"
        model={summary.model}
        modelName={summary.model_name}
        at={summary.created_at}
      />
      {summary.status === "ok" && summary.summary !== null ? (
        <div className="text-slate-800 dark:text-slate-200">
          <AiText text={summary.summary} />
        </div>
      ) : (
        <p className="font-medium text-slate-800 dark:text-slate-200">
          Withheld: {withheldText(summary.withheld_reason)}
        </p>
      )}
      <AiSources sources={summary.sources} />
    </section>
  );
}
