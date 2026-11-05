// frontend/src/settings/QuietHoursForm.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Moon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { formatRouteError } from "../pages/format.ts";

export type SettingsResponse = components["schemas"]["SettingsResponse"];
export type SettingOriginResponse =
  components["schemas"]["SettingOriginResponse"];

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

export function QuietHoursForm() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: queryKeys.settings(),
    queryFn: fetchSettings,
  });

  const settings = settingsQuery.data?.settings ?? [];
  const expectedSha256 = settingsQuery.data?.settings_file_sha256 ?? "";

  const startSetting = findSetting(
    settings,
    "notifications",
    "quiet_hours_start",
  );
  const endSetting = findSetting(settings, "notifications", "quiet_hours_end");
  const tzSetting = findSetting(
    settings,
    "notifications",
    "quiet_hours_time_zone",
  );
  const cooldownSetting = findSetting(
    settings,
    "notifications",
    "cooldown_hours",
  );

  const serverStart = String(startSetting?.value ?? "");
  const serverEnd = String(endSetting?.value ?? "");
  const serverTz = String(tzSetting?.value ?? "");
  const serverCooldown = String(cooldownSetting?.value ?? 6);

  const [draftKey, setDraftKey] = useState<string>("");
  const currentKey = `${expectedSha256}:${serverStart}:${serverEnd}:${serverTz}:${serverCooldown}`;

  const [startInput, setStartInput] = useState<string>(serverStart);
  const [endInput, setEndInput] = useState<string>(serverEnd);
  const [tzInput, setTzInput] = useState<string>(serverTz);
  const [cooldownInput, setCooldownInput] = useState<string>(serverCooldown);

  if (draftKey !== currentKey) {
    setDraftKey(currentKey);
    setStartInput(serverStart);
    setEndInput(serverEnd);
    setTzInput(serverTz);
    setCooldownInput(serverCooldown);
  }

  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{
    readonly kind: "success" | "error";
    readonly text: string;
  } | null>(null);

  const startEnv = startSetting?.origin === "environment";
  const endEnv = endSetting?.origin === "environment";
  const tzEnv = tzSetting?.origin === "environment";
  const cooldownEnv = cooldownSetting?.origin === "environment";
  const allEnv = startEnv && endEnv && tzEnv && cooldownEnv;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!expectedSha256) {
      return;
    }

    const parsedCooldown = Number(cooldownInput);
    if (!Number.isFinite(parsedCooldown) || parsedCooldown < 0 || parsedCooldown > 48) {
      setFeedback({
        kind: "error",
        text: "Cooldown hours must be a number between 0 and 48.",
      });
      return;
    }

    const changes: Array<{
      table: string;
      key: string;
      value: string | number | boolean;
    }> = [];

    if (!startEnv && startInput.trim() !== serverStart) {
      changes.push({
        table: "notifications",
        key: "quiet_hours_start",
        value: startInput.trim(),
      });
    }
    if (!endEnv && endInput.trim() !== serverEnd) {
      changes.push({
        table: "notifications",
        key: "quiet_hours_end",
        value: endInput.trim(),
      });
    }
    if (!tzEnv && tzInput.trim() !== serverTz) {
      changes.push({
        table: "notifications",
        key: "quiet_hours_time_zone",
        value: tzInput.trim(),
      });
    }
    if (!cooldownEnv && parsedCooldown !== Number(serverCooldown)) {
      changes.push({
        table: "notifications",
        key: "cooldown_hours",
        value: parsedCooldown,
      });
    }

    if (changes.length === 0) {
      setFeedback({
        kind: "success",
        text: "No quiet-hours or cooldown changes to save (changes apply on the next monitor cycle).",
      });
      return;
    }

    setSubmitting(true);
    setFeedback(null);
    try {
      const { data, error, response } = await apiClient.PUT("/api/settings", {
        body: {
          expected_sha256: expectedSha256,
          changes,
        },
      });
      if (response.ok && data) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.settings() });
        setFeedback({
          kind: "success",
          text: `Saved ${data.applied_next_cycle.join(", ")} to weatherbot.toml. Changes apply on the next monitor cycle (no restart required).`,
        });
        return;
      }
      if (response.status === 409) {
        const detail = extractErrorDetail(error, 409);
        if (detail.includes("changed on disk")) {
          void queryClient.invalidateQueries({
            queryKey: queryKeys.settings(),
          });
          setFeedback({
            kind: "error",
            text: "weatherbot.toml changed on disk since this page loaded. Reloaded the latest settings — review and save again.",
          });
        } else {
          setFeedback({
            kind: "error",
            text: detail,
          });
        }
        return;
      }
      setFeedback({
        kind: "error",
        text: extractErrorDetail(error, response.status),
      });
    } catch {
      setFeedback({
        kind: "error",
        text: formatRouteError("/api/settings"),
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section
      id="quiet-hours"
      aria-labelledby="quiet-hours-heading"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-center gap-2">
        <Moon
          className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
          aria-hidden="true"
        />
        <h2
          id="quiet-hours-heading"
          className="text-base font-bold text-slate-900 dark:text-slate-100"
        >
          Quiet Hours &amp; Cooldown
        </h2>
      </div>

      <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
        Quiet hours hold routine{" "}
        <strong>Level 1 (All Clear) and Level 2 (Monitor)</strong>{" "}
        notifications until the quiet window ends.{" "}
        <strong>
          Level 3 (Watch), Level 4 (Warning), Level 5 (Extreme Threat), and any
          upward escalation always arrive immediately.
        </strong>{" "}
        Changes saved here apply on the <strong>next monitor cycle</strong>{" "}
        without restarting <code>weatherbot serve</code>.
      </p>

      <form
        onSubmit={(event) => void handleSubmit(event)}
        className="mt-4 space-y-4 text-xs"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1">
            <label
              htmlFor="quiet-hours-start"
              className="block font-semibold text-slate-800 dark:text-slate-200"
            >
              Quiet hours start (HH:MM)
            </label>
            <input
              id="quiet-hours-start"
              type="text"
              placeholder="22:00"
              value={startInput}
              disabled={startEnv || submitting}
              onChange={(event) => setStartInput(event.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-800"
            />
            {startEnv && startSetting && (
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                Set by <code>{startSetting.variable}</code> (read-only)
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="quiet-hours-end"
              className="block font-semibold text-slate-800 dark:text-slate-200"
            >
              Quiet hours end (HH:MM)
            </label>
            <input
              id="quiet-hours-end"
              type="text"
              placeholder="07:00"
              value={endInput}
              disabled={endEnv || submitting}
              onChange={(event) => setEndInput(event.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-800"
            />
            {endEnv && endSetting && (
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                Set by <code>{endSetting.variable}</code> (read-only)
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="quiet-hours-tz"
              className="block font-semibold text-slate-800 dark:text-slate-200"
            >
              Quiet hours time zone (IANA)
            </label>
            <input
              id="quiet-hours-tz"
              type="text"
              placeholder="America/New_York (blank = location zone)"
              value={tzInput}
              disabled={tzEnv || submitting}
              onChange={(event) => setTzInput(event.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-800"
            />
            {tzEnv && tzSetting && (
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                Set by <code>{tzSetting.variable}</code> (read-only)
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="cooldown-hours"
              className="block font-semibold text-slate-800 dark:text-slate-200"
            >
              Repeat cooldown (hours, 0..48)
            </label>
            <input
              id="cooldown-hours"
              type="number"
              min={0}
              max={48}
              step="any"
              value={cooldownInput}
              disabled={cooldownEnv || submitting}
              onChange={(event) => setCooldownInput(event.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-800"
            />
            {cooldownEnv && cooldownSetting && (
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                Set by <code>{cooldownSetting.variable}</code> (read-only)
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] text-slate-500 dark:text-slate-400">
            Leave both start and end blank to disable quiet hours. Applies:{" "}
            <code>next_cycle</code>.
          </span>
          <button
            type="submit"
            disabled={allEnv || submitting || !expectedSha256}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
          >
            Save quiet hours
          </button>
        </div>

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
      </form>
    </section>
  );
}
