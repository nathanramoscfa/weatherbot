// frontend/src/settings/RetentionPanel.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { AlertDialog } from "radix-ui";
import { type FormEvent, useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { formatRouteError, formatUtc } from "../pages/format.ts";

export type RetentionResponse = components["schemas"]["RetentionResponse"];
export type SettingsResponse = components["schemas"]["SettingsResponse"];

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes.toLocaleString("en-US")} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KiB (${bytes.toLocaleString("en-US")} B)`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB (${bytes.toLocaleString("en-US")} B)`;
}

function extractErrorDetail(
  error: unknown,
  route: string,
  fallbackStatus: number,
): string {
  if (typeof error === "object" && error !== null && "detail" in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim().length > 0) {
      return detail;
    }
  }
  return formatRouteError(route, fallbackStatus);
}

async function fetchRetention(days?: number): Promise<RetentionResponse> {
  const { data, response } = await apiClient.GET(
    "/api/retention",
    days !== undefined ? { params: { query: { days } } } : {},
  );
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/retention", response.status);
  }
  return data;
}

async function fetchSettings(): Promise<SettingsResponse> {
  const { data, response } = await apiClient.GET("/api/settings");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/settings", response.status);
  }
  return data;
}

export function RetentionPanel() {
  const queryClient = useQueryClient();
  const [previewDays, setPreviewDays] = useState<number | undefined>(undefined);
  const [previewDaysInput, setPreviewDaysInput] = useState<string>("365");

  const retentionQuery = useQuery({
    queryKey: queryKeys.retention(previewDays),
    queryFn: () => fetchRetention(previewDays),
  });
  const settingsQuery = useQuery({
    queryKey: queryKeys.settings(),
    queryFn: fetchSettings,
  });

  const retention = retentionQuery.data;
  const expectedSha256 = settingsQuery.data?.settings_file_sha256 ?? "";
  const serverHistoryDays = retention?.setting?.history_days ?? 0;
  const isEnv = retention?.setting?.origin === "environment";

  const [draftKey, setDraftKey] = useState<string>("");
  const currentKey = `${expectedSha256}:${String(serverHistoryDays)}`;
  const [historyDaysInput, setHistoryDaysInput] = useState<string>(
    String(serverHistoryDays),
  );

  if (draftKey !== currentKey) {
    setDraftKey(currentKey);
    setHistoryDaysInput(String(serverHistoryDays));
    if (previewDays === undefined && retention?.plan?.days !== undefined) {
      setPreviewDaysInput(String(retention.plan.days));
    }
  }

  const [savingSetting, setSavingSetting] = useState(false);
  const [pruning, setPruning] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [feedback, setFeedback] = useState<{
    readonly kind: "success" | "error";
    readonly text: string;
  } | null>(null);

  const handleSaveHistoryDays = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!expectedSha256) {
      return;
    }
    const parsed = Number(historyDaysInput);
    if (
      !Number.isInteger(parsed) ||
      (parsed !== 0 && (parsed < 30 || parsed > 3650))
    ) {
      setFeedback({
        kind: "error",
        text: "[retention] history_days must be 0 (keep all history) or 30 to 3650 days.",
      });
      return;
    }

    setSavingSetting(true);
    setFeedback(null);
    try {
      const { data, error, response } = await apiClient.PUT("/api/settings", {
        body: {
          expected_sha256: expectedSha256,
          changes: [
            {
              table: "retention",
              key: "history_days",
              value: parsed,
            },
          ],
        },
      });
      if (response.ok && data) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.settings() });
        setFeedback({
          kind: "success",
          text:
            parsed === 0
              ? "Saved [retention] history_days = 0 (off) to weatherbot.toml. Applies at the next daily check (next_cycle)."
              : `Saved [retention] history_days = ${String(parsed)} days to weatherbot.toml. Applies at the next daily check (next_cycle).`,
        });
        return;
      }
      if (response.status === 409) {
        const detail = extractErrorDetail(error, "/api/settings", 409);
        if (detail.includes("changed on disk")) {
          void queryClient.invalidateQueries({
            queryKey: queryKeys.settings(),
          });
          setFeedback({
            kind: "error",
            text: "weatherbot.toml changed on disk since this page loaded. Reloaded the latest settings — review and save again.",
          });
        } else {
          setFeedback({ kind: "error", text: detail });
        }
        return;
      }
      setFeedback({
        kind: "error",
        text: extractErrorDetail(error, "/api/settings", response.status),
      });
    } catch {
      setFeedback({
        kind: "error",
        text: formatRouteError("/api/settings"),
      });
    } finally {
      setSavingSetting(false);
    }
  };

  const handleUpdatePreview = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsed = Number(previewDaysInput);
    if (!Number.isInteger(parsed) || parsed < 30 || parsed > 3650) {
      setFeedback({
        kind: "error",
        text: "Preview window must be an integer between 30 and 3650 days.",
      });
      return;
    }
    setFeedback(null);
    setPreviewDays(parsed);
  };

  const handlePruneNow = async () => {
    const cutoff = retention?.plan.cutoff;
    if (!cutoff) {
      return;
    }
    setPruning(true);
    setFeedback(null);
    try {
      const { data, error, response } = await apiClient.POST(
        "/api/retention/run",
        {
          body: { cutoff },
        },
      );
      if (response.ok && data) {
        setConfirmOpen(false);
        void queryClient.invalidateQueries({ queryKey: queryKeys.settings() });
        setFeedback({
          kind: "success",
          text: `Retention prune started for cutoff ${formatUtc(data.cutoff)}.`,
        });
        return;
      }
      if (response.status === 409) {
        setFeedback({
          kind: "error",
          text: extractErrorDetail(error, "/api/retention/run", 409),
        });
        return;
      }
      setFeedback({
        kind: "error",
        text: extractErrorDetail(
          error,
          "/api/retention/run",
          response.status,
        ),
      });
    } catch {
      setFeedback({
        kind: "error",
        text: formatRouteError("/api/retention/run"),
      });
    } finally {
      setPruning(false);
    }
  };

  const plan = retention?.plan;
  const nonZeroCounts = plan
    ? Object.entries(plan.counts).filter(([, count]) => count > 0)
    : [];

  return (
    <section
      id="retention"
      aria-labelledby="retention-heading"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-center gap-2">
        <Database
          className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
          aria-hidden="true"
        />
        <h2
          id="retention-heading"
          className="text-base font-bold text-slate-900 dark:text-slate-100"
        >
          Database &amp; Retention
        </h2>
      </div>

      <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
        Inspect <code>weatherbot.sqlite3</code> size, configure automatic daily
        pruning at <code>03:30</code> local time, preview what a retention
        cutoff removes, or run a manual prune. The newest snapshot, each
        location&apos;s latest assessment and active notification state,
        conditional HTTP validators, and the last 31 days of AI spend are
        always preserved.
      </p>

      {retention ? (
        <div className="mt-4 space-y-4 text-xs">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/40">
              <p className="font-semibold text-slate-700 dark:text-slate-300">
                Database size
              </p>
              <p className="mt-1 font-mono text-slate-900 dark:text-slate-100">
                {formatBytes(retention.database_bytes)}
              </p>
              <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                WAL: {formatBytes(retention.wal_bytes)}
              </p>
            </div>

            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/40">
              <p className="font-semibold text-slate-700 dark:text-slate-300">
                Snapshot range
              </p>
              <p className="mt-1 text-slate-900 dark:text-slate-100">
                Oldest:{" "}
                {retention.oldest_snapshot_at
                  ? formatUtc(retention.oldest_snapshot_at)
                  : "none"}
              </p>
              <p className="mt-0.5 text-slate-900 dark:text-slate-100">
                Newest:{" "}
                {retention.newest_snapshot_at
                  ? formatUtc(retention.newest_snapshot_at)
                  : "none"}
              </p>
            </div>

            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/40">
              <p className="font-semibold text-slate-700 dark:text-slate-300">
                Last retention run
              </p>
              {retention.last_run ? (
                <>
                  <p className="mt-1 text-slate-900 dark:text-slate-100">
                    {formatUtc(retention.last_run.ran_at)} (
                    {retention.last_run.status})
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                    Deleted{" "}
                    {retention.last_run.total_deleted.toLocaleString("en-US")}{" "}
                    rows ({String(retention.last_run.batches)} batches)
                    {retention.last_run.backup_file
                      ? ` · backup ${retention.last_run.backup_file}`
                      : ""}
                  </p>
                </>
              ) : (
                <p className="mt-1 text-slate-600 dark:text-slate-400">
                  Never run
                </p>
              )}
            </div>
          </div>

          <form
            onSubmit={(event) => void handleSaveHistoryDays(event)}
            className="flex flex-col gap-3 rounded-md border border-slate-200 p-3 sm:flex-row sm:items-end sm:justify-between dark:border-slate-800"
          >
            <div className="space-y-1">
              <label
                htmlFor="retention-history-days"
                className="block font-semibold text-slate-800 dark:text-slate-200"
              >
                Automatic retention window (<code>[retention] history_days</code>
                , 0 = off or 30..3650 days)
              </label>
              <input
                id="retention-history-days"
                type="number"
                min={0}
                max={3650}
                step={1}
                value={historyDaysInput}
                disabled={isEnv || savingSetting}
                onChange={(event) => setHistoryDaysInput(event.target.value)}
                className="w-40 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-800"
              />
              {isEnv && (
                <p className="text-[11px] text-amber-800 dark:text-amber-300">
                  Set by <code>{retention.setting.variable}</code> (read-only)
                </p>
              )}
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Applies at the next daily check (<code>next_cycle</code>).
              </p>
            </div>
            <button
              type="submit"
              disabled={isEnv || savingSetting || !expectedSha256}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
            >
              Save retention window
            </button>
          </form>

          {plan && (
            <div className="space-y-3 rounded-md border border-slate-200 bg-slate-50/50 p-3 dark:border-slate-800 dark:bg-slate-800/30">
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
                <form
                  onSubmit={handleUpdatePreview}
                  className="flex flex-wrap items-end gap-2"
                >
                  <div>
                    <label
                      htmlFor="retention-preview-days"
                      className="block font-semibold text-slate-800 dark:text-slate-200"
                    >
                      Preview plan for days (30..3650)
                    </label>
                    <input
                      id="retention-preview-days"
                      type="number"
                      min={30}
                      max={3650}
                      step={1}
                      value={previewDaysInput}
                      onChange={(event) =>
                        setPreviewDaysInput(event.target.value)
                      }
                      className="mt-1 w-28 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                    />
                  </div>
                  <button
                    type="submit"
                    className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
                  >
                    Preview plan
                  </button>
                </form>

                <AlertDialog.Root
                  open={confirmOpen}
                  onOpenChange={setConfirmOpen}
                >
                  <AlertDialog.Trigger asChild>
                    <button
                      type="button"
                      disabled={pruning}
                      className="rounded-md border border-amber-400 bg-amber-100 px-3 py-1.5 text-xs font-semibold text-amber-950 hover:bg-amber-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 disabled:cursor-not-allowed disabled:opacity-60 dark:border-amber-700 dark:bg-amber-900/70 dark:text-amber-100 dark:hover:bg-amber-900"
                    >
                      Prune now
                    </button>
                  </AlertDialog.Trigger>
                  <AlertDialog.Portal>
                    <AlertDialog.Overlay className="fixed inset-0 z-40 bg-slate-950/50" />
                    <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[min(30rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-800 shadow-lg dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                      <AlertDialog.Title className="text-sm font-bold text-slate-900 dark:text-slate-100">
                        Prune records older than {String(plan.days)} days?
                      </AlertDialog.Title>
                      <AlertDialog.Description className="mt-2 space-y-2">
                        <span className="block">
                          Cutoff: <code>{formatUtc(plan.cutoff)}</code>. This
                          prune will remove{" "}
                          <strong>
                            {plan.total_rows.toLocaleString("en-US")} rows
                          </strong>{" "}
                          (approx. {formatBytes(plan.estimated_bytes)}) across
                          history tables, after writing a pre-prune backup copy
                          of <code>weatherbot.sqlite3</code>.
                        </span>
                        {plan.kept.length > 0 && (
                          <span className="block text-slate-600 dark:text-slate-400">
                            Protected by keep-list: {plan.kept.join(", ")}.
                          </span>
                        )}
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
                            disabled={pruning}
                            onClick={() => void handlePruneNow()}
                            className="rounded-md bg-amber-700 px-3 py-1.5 font-semibold text-white hover:bg-amber-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 dark:bg-amber-500 dark:text-slate-950"
                          >
                            Confirm prune
                          </button>
                        </AlertDialog.Action>
                      </div>
                    </AlertDialog.Content>
                  </AlertDialog.Portal>
                </AlertDialog.Root>
              </div>

              <p className="text-slate-800 dark:text-slate-200">
                Plan for <strong>{String(plan.days)} days</strong> (cutoff{" "}
                <code>{formatUtc(plan.cutoff)}</code>):{" "}
                <strong>{plan.total_rows.toLocaleString("en-US")} rows</strong>{" "}
                to delete (estimated {formatBytes(plan.estimated_bytes)}).
              </p>
              {plan.kept.length > 0 && (
                <p className="text-[11px] text-slate-600 dark:text-slate-400">
                  Protected by keep-list: {plan.kept.join(", ")}.
                </p>
              )}
              {nonZeroCounts.length > 0 && (
                <ul className="grid grid-cols-2 gap-1 font-mono text-[11px] sm:grid-cols-3">
                  {nonZeroCounts.map(([table, count]) => (
                    <li
                      key={table}
                      className="rounded border border-slate-200 bg-white px-2 py-1 dark:border-slate-800 dark:bg-slate-900"
                    >
                      {table}: {count.toLocaleString("en-US")}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {feedback && (
            <div
              role={feedback.kind === "error" ? "alert" : "status"}
              className={`rounded-md border px-3 py-2 text-xs ${
                feedback.kind === "error"
                  ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
                  : "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200"
              }`}
            >
              {feedback.text}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
