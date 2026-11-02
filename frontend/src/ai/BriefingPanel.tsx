// frontend/src/ai/BriefingPanel.tsx
import { LoaderCircle, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { formatUtc } from "../pages/format.ts";
import { AiLabel } from "./AiLabel.tsx";
import { AiStateBanner } from "./AiStateBanner.tsx";
import { AiSources, AiText } from "./AiText.tsx";
import type { StoredBriefingResponse } from "./queries.ts";
import {
  isAiUnavailableReason,
  stateForReason,
  withheldText,
} from "./reasons.ts";
import type { SectionName } from "./streamEvents.ts";
import { useAiStatus } from "./useAiStatus.ts";
import { type BriefingRun, useBriefing } from "./useBriefing.ts";

export interface BriefingPanelProps {
  readonly location: string;
  readonly assessmentId: number;
  readonly assessedAt: string;
}

export function sectionHeading(name: SectionName): string {
  switch (name) {
    case "situation":
      return "Situation";
    case "what_it_means_here":
      return "What it means here";
    case "timeline":
      return "Timeline";
    case "actions":
      return "Actions";
    case "sources":
      return "Sources";
  }
}

export function WritingIndicator({ label }: { readonly label: string }) {
  return (
    <p
      role="status"
      className="inline-flex items-center gap-1.5 text-violet-800 dark:text-violet-300"
    >
      <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      <span>{label}</span>
    </p>
  );
}

function SectionBlock({
  name,
  children,
}: {
  readonly name: SectionName;
  readonly children: ReactNode;
}) {
  return (
    <div className="space-y-0.5">
      <h4 className="font-semibold text-slate-900 dark:text-slate-100">
        {sectionHeading(name)}
      </h4>
      {children}
    </div>
  );
}

function StoredBriefing({
  briefing,
}: {
  readonly briefing: StoredBriefingResponse;
}) {
  return (
    <div className="space-y-2 text-slate-800 dark:text-slate-200">
      {briefing.situation ? (
        <SectionBlock name="situation">
          <AiText text={briefing.situation} />
        </SectionBlock>
      ) : null}
      {briefing.what_it_means_here ? (
        <SectionBlock name="what_it_means_here">
          <AiText text={briefing.what_it_means_here} />
        </SectionBlock>
      ) : null}
      {briefing.timeline.length > 0 ? (
        <SectionBlock name="timeline">
          <ul className="list-disc space-y-0.5 pl-4">
            {briefing.timeline.map((item, idx) => (
              <li key={`${item.when}-${String(idx)}`} className="whitespace-pre-line">
                {item.when}: {item.what}
                {item.sources.length > 0 ? ` [${item.sources.join(", ")}]` : ""}
              </li>
            ))}
          </ul>
        </SectionBlock>
      ) : null}
      {briefing.actions.length > 0 ? (
        <SectionBlock name="actions">
          <ul className="list-disc space-y-0.5 pl-4">
            {briefing.actions.map((action, idx) => (
              <li key={String(idx)} className="whitespace-pre-line">
                {action}
              </li>
            ))}
          </ul>
        </SectionBlock>
      ) : null}
      {briefing.sources.length > 0 ? (
        <SectionBlock name="sources">
          <AiSources sources={briefing.sources} />
        </SectionBlock>
      ) : null}
    </div>
  );
}

function runNotice(run: BriefingRun): string | null {
  switch (run.phase) {
    case "unavailable":
      return isAiUnavailableReason(run.reason)
        ? null
        : `No briefing: ${run.detail ?? run.reason ?? "unavailable"}.`;
    case "failed":
      return run.status === null
        ? "The briefing stream ended before it finished."
        : `The briefing request failed (HTTP ${String(run.status)}).`;
    default:
      return null;
  }
}

export function BriefingPanel({
  location,
  assessmentId,
  assessedAt,
}: BriefingPanelProps) {
  const status = useAiStatus();
  const { stored, loading, failed, run, running, busy, brief } =
    useBriefing(location);
  const ai = status.data;
  const ready = ai?.state === "ready";

  let banner: ReactNode = null;
  if (run.phase === "refused") {
    banner = (
      <AiStateBanner
        state={stateForReason(run.reason)}
        reason={run.reason}
        capMicroUsd={ai?.today.cap_micro_usd}
      />
    );
  } else if (run.phase === "unavailable" && isAiUnavailableReason(run.reason)) {
    banner = (
      <AiStateBanner
        state={stateForReason(run.reason)}
        reason={run.reason}
        capMicroUsd={ai?.today.cap_micro_usd}
      />
    );
  } else if (ai && ai.state !== "ready") {
    banner = (
      <AiStateBanner
        state={ai.state}
        reason={ai.reason}
        capMicroUsd={ai.today.cap_micro_usd}
      />
    );
  }

  const stale = stored?.stale === true;
  const withheld = stored?.status === "withheld";
  const again = stale || withheld;
  const fresh = stored !== null && !again;
  const notice = runNotice(run);
  const showStored = stored !== null && !running && run.phase !== "withheld";

  return (
    <section
      aria-label={`AI briefing for ${location}`}
      className="space-y-2 rounded-md border border-violet-200 bg-violet-50/50 p-3 text-xs dark:border-violet-900/70 dark:bg-violet-950/20"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="inline-flex items-center gap-1.5 font-semibold text-slate-900 dark:text-slate-100">
          <Sparkles
            className="h-4 w-4 shrink-0 text-violet-700 dark:text-violet-300"
            aria-hidden="true"
          />
          AI briefing
        </h3>
        <button
          type="button"
          onClick={() => brief(fresh)}
          disabled={busy || !ready}
          className="rounded-md bg-violet-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-violet-500 dark:text-slate-950 dark:hover:bg-violet-400"
        >
          {again ? "Brief me again" : "Brief me"}
        </button>
      </div>

      {banner}

      {status.isError ? (
        <p className="text-slate-600 dark:text-slate-400">
          The AI's state could not be read (/api/ai).
        </p>
      ) : null}

      {run.phase === "streaming" ? (
        <div className="space-y-2">
          {run.start ? (
            <AiLabel
              kind="AI briefing"
              model={run.start.model}
              modelName={run.start.modelName}
              context={
                run.start.asOf
                  ? `for the ${formatUtc(run.start.asOf)} assessment`
                  : null
              }
            />
          ) : null}
          <div className="space-y-2 text-slate-800 dark:text-slate-200">
            {run.sections.map((section) => (
              <SectionBlock key={section.name} name={section.name}>
                <AiText text={section.text} />
              </SectionBlock>
            ))}
          </div>
          <WritingIndicator label="Writing the briefing…" />
        </div>
      ) : null}

      {run.phase === "withheld" ? (
        <p
          role="status"
          className="rounded-md border border-slate-300 bg-white px-3 py-2 font-medium text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
        >
          Withheld: {run.detail ?? withheldText(run.reason)}
        </p>
      ) : null}

      {notice ? (
        <p role="status" className="text-slate-700 dark:text-slate-300">
          {notice}
        </p>
      ) : null}

      {loading ? (
        <p className="text-slate-600 dark:text-slate-400">
          Loading the stored briefing…
        </p>
      ) : null}
      {failed ? (
        <p className="text-slate-600 dark:text-slate-400">
          The stored briefing could not be read (/api/ai/briefings).
        </p>
      ) : null}

      {showStored ? (
        <div className="space-y-2">
          <AiLabel
            kind="AI briefing"
            model={stored.model}
            modelName={stored.model_name}
            at={stored.created_at}
            context={
              stored.assessment_id === assessmentId
                ? `for the ${formatUtc(assessedAt)} assessment`
                : `for assessment no. ${String(stored.assessment_id ?? "?")}`
            }
          />
          {stale ? (
            <p
              role="note"
              className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950 dark:border-amber-700/80 dark:bg-amber-950/60 dark:text-amber-100"
            >
              Stale: this briefing was written for assessment no.{" "}
              {String(stored.assessment_id ?? "?")}; the level above comes from
              the newer assessment no. {String(assessmentId)} (
              {formatUtc(assessedAt)}). Press Brief me again for a current one.
            </p>
          ) : null}
          {withheld ? (
            <p className="rounded-md border border-slate-300 bg-white px-3 py-2 font-medium text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
              Withheld: {withheldText(stored.withheld_reason)}
            </p>
          ) : (
            <StoredBriefing briefing={stored} />
          )}
        </div>
      ) : null}

      {stored === null && !loading && !failed && run.phase === "idle" && ready ? (
        <p className="text-slate-600 dark:text-slate-400">
          No briefing yet. Brief me asks Claude to explain this assessment in
          plain words.
        </p>
      ) : null}
    </section>
  );
}
