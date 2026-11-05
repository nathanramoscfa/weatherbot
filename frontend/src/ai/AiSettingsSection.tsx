// frontend/src/ai/AiSettingsSection.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { AlertDialog } from "radix-ui";
import { type FormEvent, useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
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

type SettingsResponse = components["schemas"]["SettingsResponse"];
type SettingOriginResponse = components["schemas"]["SettingOriginResponse"];

async function fetchSettings(): Promise<SettingsResponse> {
  const { data, response } = await apiClient.GET("/api/settings");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/settings", response.status);
  }
  return data;
}

function findSetting(
  settings: readonly SettingOriginResponse[],
  table: string,
  key: string,
): SettingOriginResponse | undefined {
  return settings.find((item) => item.table === table && item.key === key);
}

function extractErrorDetail(error: unknown, fallbackStatus: number): string {
  if (typeof error === "object" && error !== null && "detail" in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim().length > 0) {
      return detail;
    }
  }
  return formatRouteError("/api/settings", fallbackStatus);
}

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
  const settingsQuery = useQuery({
    queryKey: queryKeys.settings(),
    queryFn: fetchSettings,
  });
  const [pending, setPending] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [configSaving, setConfigSaving] = useState(false);
  const [configFeedback, setConfigFeedback] = useState<Feedback | null>(null);

  const ai = status.data;
  const calls = callsQuery.data?.calls ?? [];
  const settingsList = settingsQuery.data?.settings ?? [];
  const expectedSha256 = settingsQuery.data?.settings_file_sha256 ?? "";

  const enabledSetting = findSetting(settingsList, "ai", "enabled");
  const capSetting = findSetting(settingsList, "ai", "daily_cap_usd");
  const summariesSetting = findSetting(settingsList, "ai", "change_summaries");
  const narrationSetting = findSetting(settingsList, "ai", "outlook_narration");

  const serverEnabled = Boolean(enabledSetting?.value ?? true);
  const serverCap = String(capSetting?.value ?? 1);
  const serverSummaries = Boolean(summariesSetting?.value ?? true);
  const serverNarration = Boolean(narrationSetting?.value ?? false);

  const [draftKey, setDraftKey] = useState<string>("");
  const currentKey = `${expectedSha256}:${String(serverEnabled)}:${serverCap}:${String(serverSummaries)}:${String(serverNarration)}`;

  const [enabledInput, setEnabledInput] = useState<boolean>(serverEnabled);
  const [capInput, setCapInput] = useState<string>(serverCap);
  const [summariesInput, setSummariesInput] =
    useState<boolean>(serverSummaries);
  const [narrationInput, setNarrationInput] =
    useState<boolean>(serverNarration);

  if (draftKey !== currentKey) {
    setDraftKey(currentKey);
    setEnabledInput(serverEnabled);
    setCapInput(serverCap);
    setSummariesInput(serverSummaries);
    setNarrationInput(serverNarration);
  }

  const enabledEnv = enabledSetting?.origin === "environment";
  const capEnv = capSetting?.origin === "environment";
  const summariesEnv = summariesSetting?.origin === "environment";
  const narrationEnv = narrationSetting?.origin === "environment";
  const allAiEnv = enabledEnv && capEnv && summariesEnv && narrationEnv;

  const handleSaveAiConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!expectedSha256) {
      return;
    }
    const parsedCap = Number(capInput);
    if (!Number.isFinite(parsedCap) || parsedCap <= 0 || parsedCap > 100) {
      setConfigFeedback({
        kind: "error",
        text: "Daily cap (USD) must be greater than 0 and at most 100.",
      });
      return;
    }

    const changes: Array<{
      table: string;
      key: string;
      value: string | number | boolean;
    }> = [];
    if (!enabledEnv && enabledInput !== serverEnabled) {
      changes.push({ table: "ai", key: "enabled", value: enabledInput });
    }
    if (!capEnv && parsedCap !== Number(serverCap)) {
      changes.push({ table: "ai", key: "daily_cap_usd", value: parsedCap });
    }
    if (!summariesEnv && summariesInput !== serverSummaries) {
      changes.push({
        table: "ai",
        key: "change_summaries",
        value: summariesInput,
      });
    }
    if (!narrationEnv && narrationInput !== serverNarration) {
      changes.push({
        table: "ai",
        key: "outlook_narration",
        value: narrationInput,
      });
    }

    if (changes.length === 0) {
      setConfigFeedback({
        kind: "success",
        text: "No AI setting changes to save (changes apply on the next monitor start).",
      });
      return;
    }

    setConfigSaving(true);
    setConfigFeedback(null);
    try {
      const { data, error, response } = await apiClient.PUT("/api/settings", {
        body: {
          expected_sha256: expectedSha256,
          changes,
        },
      });
      if (response.ok && data) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.settings() });
        setConfigFeedback({
          kind: "success",
          text: `Saved ${data.applied_next_start.join(", ")} to weatherbot.toml. Restart weatherbot serve to apply (next_start).`,
        });
        return;
      }
      if (response.status === 409) {
        const detail = extractErrorDetail(error, 409);
        if (detail.includes("changed on disk")) {
          void queryClient.invalidateQueries({
            queryKey: queryKeys.settings(),
          });
          setConfigFeedback({
            kind: "error",
            text: "weatherbot.toml changed on disk since this page loaded. Reloaded the latest settings — review and save again.",
          });
        } else {
          setConfigFeedback({ kind: "error", text: detail });
        }
        return;
      }
      setConfigFeedback({
        kind: "error",
        text: extractErrorDetail(error, response.status),
      });
    } catch {
      setConfigFeedback({
        kind: "error",
        text: formatRouteError("/api/settings"),
      });
    } finally {
      setConfigSaving(false);
    }
  };

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

      <form
        onSubmit={(event) => void handleSaveAiConfig(event)}
        className="mt-4 space-y-3 border-t border-slate-200 pt-4 text-xs dark:border-slate-800"
      >
        <h3 className="font-semibold text-slate-900 dark:text-slate-100">
          AI Configuration (<code>weatherbot.toml</code>)
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1">
            <label
              htmlFor="ai-enabled-input"
              className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200"
            >
              <input
                id="ai-enabled-input"
                type="checkbox"
                checked={enabledInput}
                disabled={enabledEnv || configSaving}
                onChange={(event) => setEnabledInput(event.target.checked)}
                className="h-3.5 w-3.5 rounded border-slate-300 text-violet-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700"
              />
              AI enabled (<code>[ai] enabled</code>)
            </label>
            {enabledEnv && enabledSetting && (
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                Set by <code>{enabledSetting.variable}</code> (read-only)
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="ai-daily-cap-input"
              className="block font-semibold text-slate-800 dark:text-slate-200"
            >
              Daily cap USD (<code>daily_cap_usd</code>)
            </label>
            <input
              id="ai-daily-cap-input"
              type="number"
              min={0.01}
              max={100}
              step="any"
              value={capInput}
              disabled={capEnv || configSaving}
              onChange={(event) => setCapInput(event.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-800"
            />
            {capEnv && capSetting && (
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                Set by <code>{capSetting.variable}</code> (read-only)
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="ai-change-summaries-input"
              className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200"
            >
              <input
                id="ai-change-summaries-input"
                type="checkbox"
                checked={summariesInput}
                disabled={summariesEnv || configSaving}
                onChange={(event) => setSummariesInput(event.target.checked)}
                className="h-3.5 w-3.5 rounded border-slate-300 text-violet-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700"
              />
              Change summaries (<code>[ai] change_summaries</code>)
            </label>
            {summariesEnv && summariesSetting && (
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                Set by <code>{summariesSetting.variable}</code> (read-only)
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="ai-outlook-narration-input"
              className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200"
            >
              <input
                id="ai-outlook-narration-input"
                type="checkbox"
                checked={narrationInput}
                disabled={narrationEnv || configSaving}
                onChange={(event) => setNarrationInput(event.target.checked)}
                className="h-3.5 w-3.5 rounded border-slate-300 text-violet-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700"
              />
              Outlook narration (<code>[ai] outlook_narration</code>)
            </label>
            {narrationEnv && narrationSetting && (
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                Set by <code>{narrationSetting.variable}</code> (read-only)
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] text-slate-500 dark:text-slate-400">
            Applies on the next monitor start (<code>next_start</code>).
          </span>
          <button
            type="submit"
            disabled={allAiEnv || configSaving || !expectedSha256}
            className="rounded-md bg-violet-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-violet-500 dark:text-slate-950"
          >
            Save AI settings
          </button>
        </div>

        {configFeedback && (
          <div
            role={configFeedback.kind === "error" ? "alert" : "status"}
            className={`rounded-md border px-3 py-2 text-xs ${
              configFeedback.kind === "error"
                ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
                : "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200"
            }`}
          >
            {configFeedback.text}
          </div>
        )}
      </form>
    </section>
  );
}
