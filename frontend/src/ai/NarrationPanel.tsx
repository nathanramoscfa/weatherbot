// frontend/src/ai/NarrationPanel.tsx
import { Sparkles } from "lucide-react";
import type { components } from "../api/schema.ts";
import { AiLabel } from "./AiLabel.tsx";
import { AiStateBanner } from "./AiStateBanner.tsx";
import { AiSources, AiText } from "./AiText.tsx";
import { WritingIndicator } from "./BriefingPanel.tsx";
import { basinName, horizonName } from "./format.ts";
import type { AiStatusResponse, StoredNarrationResponse } from "./queries.ts";
import {
  isAiUnavailableReason,
  stateForReason,
  withheldText,
} from "./reasons.ts";
import { useNarration, type WrittenNarration } from "./useNarration.ts";

type Basin = components["schemas"]["Basin"];
type Horizon = components["schemas"]["Horizon"];

export const NARRATION_NOTE =
  "AI-generated · may be wrong · the official graphic above governs";

export interface NarrationPanelProps {
  readonly basin: Basin;
  readonly horizon: Horizon;
  readonly label: string;
  readonly stored: StoredNarrationResponse | null;
  readonly ai: AiStatusResponse | undefined;
}

function Narration({
  label,
  narration,
  two,
}: {
  readonly label: string;
  readonly narration: WrittenNarration;
  readonly two: StoredNarrationResponse["two"];
}) {
  return (
    <div className="space-y-1.5">
      <AiLabel
        kind={label}
        model={narration.model}
        modelName={narration.modelName}
        at={narration.createdAt}
        note={NARRATION_NOTE}
      />
      <div className="space-y-1.5 text-slate-800 dark:text-slate-200">
        {narration.summary ? <AiText text={narration.summary} /> : null}
        {narration.areas.length > 0 ? (
          <ul className="list-disc space-y-0.5 pl-4">
            {narration.areas.map((area, idx) => (
              <li key={String(idx)} className="whitespace-pre-line">
                {area.description} — chance: {area.chance_text}
              </li>
            ))}
          </ul>
        ) : null}
        {narration.caveat ? (
          <AiText
            text={narration.caveat}
            className="text-slate-600 italic dark:text-slate-400"
          />
        ) : null}
        {two ? (
          <div>
            <p className="font-semibold">Checked against</p>
            <AiSources sources={[two]} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function NarrationPanel({
  basin,
  horizon,
  label,
  stored,
  ai,
}: NarrationPanelProps) {
  const { run, busy, interpret } = useNarration(basin, horizon);
  const ready = ai?.state === "ready";
  const storedOk = stored?.status === "ok" ? stored : null;
  const written: WrittenNarration | null = storedOk
    ? {
        model: storedOk.model,
        modelName: storedOk.model_name,
        createdAt: storedOk.created_at,
        summary: storedOk.summary,
        areas: storedOk.areas,
        caveat: storedOk.caveat,
      }
    : run.phase === "done"
      ? run.narration
      : null;
  const capMicroUsd = ai?.today.cap_micro_usd;
  const reason =
    run.phase === "refused" ||
    (run.phase === "unavailable" && isAiUnavailableReason(run.reason))
      ? run.reason
      : null;

  return (
    <section
      aria-label={`${label}: ${basinName(basin)} ${horizonName(horizon)}`}
      className="space-y-2 rounded-md border border-violet-200 bg-violet-50/50 p-2.5 text-xs dark:border-violet-900/70 dark:bg-violet-950/20"
    >
      {written ? (
        <Narration label={label} narration={written} two={storedOk?.two ?? null} />
      ) : null}

      {!written && stored?.status === "withheld" && run.phase === "idle" ? (
        <p className="font-medium text-slate-800 dark:text-slate-200">
          Withheld: {withheldText(stored.withheld_reason)}
        </p>
      ) : null}

      {run.phase === "streaming" ? (
        <WritingIndicator label="Interpreting the graphic…" />
      ) : null}
      {run.phase === "withheld" ? (
        <p
          role="status"
          className="font-medium text-slate-800 dark:text-slate-200"
        >
          Withheld: {run.detail ?? withheldText(run.reason)}
        </p>
      ) : null}
      {isAiUnavailableReason(reason) ? (
        <AiStateBanner
          state={stateForReason(reason)}
          reason={reason}
          capMicroUsd={capMicroUsd}
        />
      ) : null}
      {run.phase === "unavailable" && reason === null ? (
        <p role="status" className="text-slate-700 dark:text-slate-300">
          No interpretation: {run.detail ?? run.reason ?? "unavailable"}.
        </p>
      ) : null}
      {run.phase === "failed" ? (
        <p role="status" className="text-slate-700 dark:text-slate-300">
          {run.status === null
            ? "The interpretation stream ended before it finished."
            : `The interpretation request failed (HTTP ${String(run.status)}).`}
        </p>
      ) : null}

      {!written && run.phase !== "streaming" ? (
        <button
          type="button"
          onClick={interpret}
          disabled={busy || !ready}
          aria-label={`Interpret (AI) the ${basinName(basin)} ${horizonName(horizon)} outlook`}
          className="inline-flex items-center gap-1.5 rounded-md bg-violet-700 px-2.5 py-1 text-xs font-semibold text-white hover:bg-violet-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-violet-500 dark:text-slate-950 dark:hover:bg-violet-400"
        >
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          Interpret (AI)
        </button>
      ) : null}
    </section>
  );
}
