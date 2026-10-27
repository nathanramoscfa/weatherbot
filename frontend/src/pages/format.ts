// frontend/src/pages/format.ts
import type { components } from "../api/schema";

type ArrivalReadingResponse = components["schemas"]["ArrivalReadingResponse"];
type BreakpointSpan = components["schemas"]["BreakpointSpan"];
type WindReadingResponse = components["schemas"]["WindReadingResponse"];

export type JsonFixture<T> = T extends string
  ? string
  : T extends number
    ? number
    : T extends boolean
      ? boolean
      : T extends readonly (infer U)[]
        ? readonly JsonFixture<U>[]
        : T extends object
          ? { readonly [K in keyof T]: JsonFixture<T[K]> }
          : T;

export function asSchema<T>(fixture: JsonFixture<T>): T {
  return fixture as unknown as T;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatUtc(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  const year = date.getUTCFullYear();
  const month = pad2(date.getUTCMonth() + 1);
  const day = pad2(date.getUTCDate());
  const hour = pad2(date.getUTCHours());
  const minute = pad2(date.getUTCMinutes());
  return `${String(year)}-${month}-${day} ${hour}:${minute} UTC`;
}

export function formatLocal(
  iso: string | null | undefined,
  timeZone: string | null | undefined,
): string | null {
  if (!iso || !timeZone) {
    return null;
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  try {
    const formatter = new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZoneName: "short",
    });
    const parts = formatter.formatToParts(date);
    const get = (type: Intl.DateTimeFormatPartTypes): string =>
      parts.find((p) => p.type === type)?.value ?? "";
    const hourRaw = get("hour");
    const hour = hourRaw === "24" ? "00" : hourRaw;
    const tzName = get("timeZoneName");
    return `${get("year")}-${get("month")}-${get("day")} ${hour}:${get("minute")}${tzName ? ` ${tzName}` : ""}`;
  } catch {
    return null;
  }
}

export function formatBothTimes(
  iso: string | null | undefined,
  timeZone?: string | null,
): string {
  const utc = formatUtc(iso);
  const local = formatLocal(iso, timeZone);
  if (!local || local === utc) {
    return utc;
  }
  return `${utc} (${local})`;
}

export function formatKm(km: number): string {
  return `${km.toFixed(1)} km`;
}

export function formatBearing(deg: number): string {
  return `${String(Math.round(deg))} deg`;
}

export function formatLeadHours(hours: number): string {
  return `${hours.toFixed(1)} h`;
}

export function formatAgeSeconds(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  if (whole < 60) {
    return `${String(whole)} s old`;
  }
  const minutes = Math.floor(whole / 60);
  if (minutes < 60) {
    return `${String(minutes)} min old`;
  }
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  if (remMinutes === 0) {
    return `${String(hours)} h old`;
  }
  return `${String(hours)} h ${String(remMinutes)} min old`;
}

export function formatArrivalOrigin(reading: ArrivalReadingResponse): string {
  const adv = reading.advisory ?? "?";
  if (reading.origin === "kmz") {
    return `kmz, adv ${adv}`;
  }
  if (reading.origin === "map_layer") {
    return `map layer, adv ${adv}`;
  }
  return "track closest approach, not a wind arrival";
}

export function formatArrivalReading(
  reading: ArrivalReadingResponse,
  timeZone?: string | null,
): string {
  const origin = formatArrivalOrigin(reading);
  switch (reading.reading) {
    case "outside":
      return `outside the 5% contour (${origin})`;
    case "between":
      return `${formatBothTimes(reading.start, timeZone)} to ${formatBothTimes(reading.end, timeZone)} (${origin})`;
    case "before":
      return `by ${formatBothTimes(reading.end, timeZone)} (${origin})`;
    case "after":
      return `after ${formatBothTimes(reading.start, timeZone)} (${origin})`;
    case "track":
      return `${formatBothTimes(reading.approach_at, timeZone)} (${origin})`;
    case "unresolved":
      return `unresolved (${origin}): ${reading.reason ?? "unknown reason"}`;
  }
}

export function formatWindProbability(item: WindReadingResponse): string {
  if (item.reading === "band") {
    return `${item.label ?? "?"} (at least ${String(item.lower_pct ?? 0)}%)`;
  }
  if (item.reading === "below_every_band") {
    return "<5% (below every band)";
  }
  return "outside product coverage";
}

export function formatBreakpointSpan(
  span: BreakpointSpan | null | undefined,
): string {
  if (!span || span.names.length === 0) {
    return "none within the coastal reach";
  }
  if (span.is_region || span.names.length === 1) {
    return `${span.names[0] ?? ""} (${span.country})`;
  }
  return `${span.names[0] ?? ""} to ${span.names[1] ?? ""} (${span.country})`;
}

export function formatRouteError(route: string, status?: number): string {
  if (status !== undefined) {
    return `Request to ${route} failed (HTTP ${String(status)}).`;
  }
  return `Request to ${route} failed.`;
}
