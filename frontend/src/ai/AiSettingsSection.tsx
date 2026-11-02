// frontend/src/ai/AiSettingsSection.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { AlertDialog } from "radix-ui";
import { useState } from "react";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import { formatRouteError, formatUtc } from "../pages/format.ts";
import { AiStateBanner } from "./AiStateBanner.tsx";
import {
  credentialSourceText,
  formatCount,
  formatUsd,
  formatUsdPrecise,
  modelDisplayName,
} from "./format.ts";
import {
  type AiCallResponse,
  type AiStatusResponse,
  fetchAiCalls,
} from "./queries.ts";
import { type AiStateName, reasonText } from "./reasons.ts";
import { useAiStatus } from "./useAiStatus.ts";

const MICRO_PER_USD = 1_000_000;
const ALLOWANCES_PER_DAY = 3;

interface Feedback {
  readonly kind: "success" | "error";
  readonly text: string;
}

export function stateName(state: AiStateName): string {
  switch (state) {
    case "off":
      return "Off";
    case "ready":
      return "Ready";
    case "paused":
      return "Paused";
    case "capped":
      return "Capped";
    case "unavailable":
      return "Unavailable";
  }
}

function callCost(call: AiCallResponse): string {
  if (call.allowance_micro_usd > 0) {
    return `+${formatUsd(call.allowance_micro_usd)} allowance`;
  }
  if (call.cost_micro_usd === null) {
    return "reserved";
  }
  return formatUsdPrecise(call.cost_micro_usd);
}

function callTokens(call: AiCallResponse): string {
  if (call.model === null) {
    return "—";
  }
  const cache = call.cache_write_tokens + call.cache_read_tokens;
  return `${formatCount(call.input_tokens)} in · ${formatCount(cache)} cache · ${formatCount(call.output_tokens)} out`;
}

function Meter({ ai }: { readonly ai: AiStatusResponse }) {
  const { today } = ai;
  const limit = today.cap_micro_usd + today.allowance_micro_usd;
  const used = today.spent_micro_usd + today.reserved_micro_usd;
  const max = Math.max(limit, 1);
  return (
    <div className="space-y-1">
      <p className="font-semibold text-slate-900 dark:text-slate-100">
        Today ({today.day})
      </p>
      <meter
        min={0}
        max={max}
        low={max * 0.5}
        high={max * 0.8}
        optimum={0}
        value={Math.min(used, max)}
        aria-label="Today's AI spend against today's limit"
        className="block h-3 w-full"
      />
      <p className="text-slate-700 dark:text-slate-300">
        Spent {formatUsdPrecise(today.spent_micro_usd)} · reserved{" "}
        {formatUsdPrecise(today.reserved_micro_usd)} · limit {formatUsd(limit)}{" "}
        (cap {formatUsd(today.cap_micro_usd)} + allowance{" "}
        {formatUsd(today.allowance_micro_usd)}) · {formatCount(today.calls)}{" "}
        {today.calls === 1 ? "request" : "requests"}
      </p>
      <p className="text-slate-600 dark:text-slate-400">
        Tokens: {formatCount(today.input_tokens)} input ·{" "}
        {formatCount(today.cache_write_tokens)} cache write ·{" "}
        {formatCount(today.cache_read_tokens)} cache read ·{" "}
        {formatCount(today.output_tokens)} output
      </p>
    </div>
  );
}

export function AiSettingsSection() {
  const queryClient = useQueryClient();
  const status = useAiStatus();
  const callsQuery = useQuery({
    queryKey: queryKeys.aiCalls(),
    queryFn: fetchAiCalls,
  });
  const [pending, setPending] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const ai = status.data;
  const calls = callsQuery.data?.calls ?? [];

  const applyStatus = async (next: AiStatusResponse) => {
    queryClient.setQueryData(queryKeys.ai(), next);
    await queryClient.invalidateQueries({ queryKey: queryKeys.aiCalls() });
  };

  const handlePause = async () => {
    if (!ai) {
      return;
    }
    const paused = !ai.paused;
    setPending(true);
    setFeedback(null);
    try {
      const { data, response } = await apiClient.PUT("/api/ai/pause", {
        body: { paused },
      });
      if (response.ok && data) {
        await applyStatus(data);
        setFeedback({
          kind: "success",
          text: paused ? "AI paused." : "AI resumed.",
        });
      } else if (response.status === 503) {
        setFeedback({
          kind: "error",
          text: "AI is off: there is no AI service to pause (/api/ai/pause returned HTTP 503).",
        });
      } else {
        setFeedback({
          kind: "error",
          text: formatRouteError("/api/ai/pause", response.status),
        });
      }
    } catch {
      setFeedback({ kind: "error", text: formatRouteError("/api/ai/pause") });
    } finally {
      setPending(false);
    }
  };

  const handleAllow = async () => {
    if (!ai) {
      return;
    }
    const amount = ai.today.cap_micro_usd;
    setPending(true);
    setFeedback(null);
    try {
      const { data, response } = await apiClient.POST("/api/ai/allowance", {
        body: { usd: amount / MICRO_PER_USD },
      });
      if (response.ok && data) {
        await applyStatus(data);
        setFeedback({
          kind: "success",
          text: `Allowed ${formatUsd(amount)} more today.`,
        });
      } else if (response.status === 409) {
        setFeedback({
          kind: "error",
          text: "Today's three allowances are used (/api/ai/allowance returned HTTP 409).",
        });
      } else if (response.status === 503) {
        setFeedback({
          kind: "error",
          text: "AI is off: there is no AI service (/api/ai/allowance returned HTTP 503).",
        });
      } else {
        setFeedback({
          kind: "error",
          text: formatRouteError("/api/ai/allowance", response.status),
        });
      }
    } catch {
      setFeedback({
        kind: "error",
        text: formatRouteError("/api/ai/allowance"),
      });
    } finally {
      setPending(false);
    }
  };

  const controllable = ai !== undefined && ai.credential_source !== null;
  const allowance = ai ? formatUsd(ai.today.cap_micro_usd) : "";
  const raisedLimit = ai
    ? formatUsd(
        ai.today.cap_micro_usd * 2 + ai.today.allowance_micro_usd,
      )
    : "";

  return (
    <section
      id="ai"
      aria-labelledby="ai-heading"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-center gap-2">
        <Sparkles
          className="h-5 w-5 shrink-0 text-violet-700 dark:text-violet-300"
          aria-hidden="true"
        />
        <h2
          id="ai-heading"
          className="text-base font-bold text-slate-900 dark:text-slate-100"
        >
          AI
        </h2>
      </div>
      <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
        Claude explains what the engine decided and never sets a level. Every
        request is metered here and held under the daily cap; the cap itself
        changes only in <code>weatherbot.toml</code> or{" "}
        <code>WEATHERBOT_AI_DAILY_CAP_USD</code>.
      </p>

      {status.isError ? (
        <p role="alert" className="mt-3 text-xs text-red-800 dark:text-red-300">
          {formatRouteError("/api/ai")}
        </p>
      ) : null}

      {ai ? (
        <div className="mt-3 space-y-4 text-xs">
          <div className="space-y-2">
            <p className="text-slate-800 dark:text-slate-200">
              State: <strong>{stateName(ai.state)}</strong>
              {ai.reason ? ` (${reasonText(ai.reason)})` : ""}
            </p>
            <AiStateBanner
              state={ai.state}
              reason={ai.reason}
              capMicroUsd={ai.today.cap_micro_usd}
            />
            <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-[max-content_1fr]">
              <dt className="font-medium text-slate-600 dark:text-slate-400">
                Credential
              </dt>
              <dd className="text-slate-800 dark:text-slate-200">
                {credentialSourceText(ai.credential_source)}
              </dd>
              <dt className="font-medium text-slate-600 dark:text-slate-400">
                Briefings, chat, narrations
              </dt>
              <dd className="text-slate-800 dark:text-slate-200">
                {modelDisplayName(ai.models.model, ai.models.model_name)} (
                <code>{ai.models.model}</code>)
              </dd>
              <dt className="font-medium text-slate-600 dark:text-slate-400">
                Change summaries
              </dt>
              <dd className="text-slate-800 dark:text-slate-200">
                {ai.features.change_summaries ? "On" : "Off"} ·{" "}
                {modelDisplayName(
                  ai.models.summary_model,
                  ai.models.summary_model_name,
                )}{" "}
                (<code>{ai.models.summary_model}</code>)
              </dd>
              <dt className="font-medium text-slate-600 dark:text-slate-400">
                Outlook narration
              </dt>
              <dd className="text-slate-800 dark:text-slate-200">
                {ai.features.outlook_narration ? "On" : "Off"}
              </dd>
            </dl>
          </div>

          <Meter ai={ai} />

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={!controllable || pending}
              onClick={() => void handlePause()}
              className="rounded-md border border-slate-300 bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              {ai.paused ? "Resume AI" : "Pause AI"}
            </button>

            <AlertDialog.Root open={confirmOpen} onOpenChange={setConfirmOpen}>
              <AlertDialog.Trigger asChild>
                <button
                  type="button"
                  disabled={
                    !controllable || pending || ai.today.allowances_left === 0
                  }
                  className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
                >
                  Allow {allowance} more today
                </button>
              </AlertDialog.Trigger>
              <AlertDialog.Portal>
                <AlertDialog.Overlay className="fixed inset-0 z-40 bg-slate-950/50" />
                <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-800 shadow-lg dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                  <AlertDialog.Title className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Allow {allowance} more today?
                  </AlertDialog.Title>
                  <AlertDialog.Description className="mt-2">
                    Today&apos;s AI limit rises to {raisedLimit} until midnight.{" "}
                    {String(ai.today.allowances_left)} of{" "}
                    {String(ALLOWANCES_PER_DAY)} allowances are left today.
                  </AlertDialog.Description>
                  <div className="mt-4 flex justify-end gap-2">
                    <AlertDialog.Cancel asChild>
                      <button
                        type="button"
                        className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                      >
                        Cancel
                      </button>
                    </AlertDialog.Cancel>
                    <AlertDialog.Action asChild>
                      <button
                        type="button"
                        onClick={() => void handleAllow()}
                        className="rounded-md bg-violet-700 px-3 py-1.5 font-semibold text-white hover:bg-violet-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 dark:bg-violet-500 dark:text-slate-950"
                      >
                        Allow {allowance} more
                      </button>
                    </AlertDialog.Action>
                  </div>
                </AlertDialog.Content>
              </AlertDialog.Portal>
            </AlertDialog.Root>

            <span className="text-slate-600 dark:text-slate-400">
              {String(ai.today.allowances_left)} of{" "}
              {String(ALLOWANCES_PER_DAY)} allowances left today
            </span>
          </div>

          {feedback ? (
            <div
              role={feedback.kind === "error" ? "alert" : "status"}
              className={`rounded-md border px-3 py-2 ${
                feedback.kind === "error"
                  ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
                  : "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200"
              }`}
            >
              {feedback.text}
            </div>
          ) : null}

          <div className="space-y-1">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">
              Recent requests
            </h3>
            {calls.length === 0 ? (
              <p className="text-slate-600 dark:text-slate-400">
                No AI request is recorded yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-600 dark:border-slate-800 dark:text-slate-400">
                      <th className="py-1.5 pr-3 font-semibold">Kind</th>
                      <th className="py-1.5 pr-3 font-semibold">Model</th>
                      <th className="py-1.5 pr-3 font-semibold">Tokens</th>
                      <th className="py-1.5 pr-3 font-semibold">Cost</th>
                      <th className="py-1.5 pr-3 font-semibold">Status</th>
                      <th className="py-1.5 font-semibold">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                    {calls.map((call) => (
                      <tr key={call.id}>
                        <td className="py-1.5 pr-3 text-slate-900 dark:text-slate-100">
                          {call.kind}
                          {call.location ? ` · ${call.location}` : ""}
                        </td>
                        <td className="py-1.5 pr-3 text-slate-800 dark:text-slate-200">
                          {call.model ? modelDisplayName(call.model) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-slate-700 dark:text-slate-300">
                          {callTokens(call)}
                        </td>
                        <td className="py-1.5 pr-3 font-mono text-slate-800 dark:text-slate-200">
                          {callCost(call)}
                        </td>
                        <td className="py-1.5 pr-3 text-slate-700 dark:text-slate-300">
                          {call.status}
                          {call.error_kind ? ` (${call.error_kind})` : ""}
                        </td>
                        <td className="py-1.5 text-slate-600 dark:text-slate-400">
                          {formatUtc(call.started_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
