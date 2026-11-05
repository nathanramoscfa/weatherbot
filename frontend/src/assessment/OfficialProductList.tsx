// frontend/src/assessment/OfficialProductList.tsx
import type { components } from "../api/schema.ts";
import { formatBothTimes, formatKm } from "../pages/format.ts";

type AssessmentOfficialProductResponse =
  components["schemas"]["AssessmentOfficialProductResponse"];

export interface OfficialProductListProps {
  readonly official: readonly AssessmentOfficialProductResponse[];
  readonly timeZone: string | null | undefined;
}

export function OfficialProductList({
  official,
  timeZone,
}: OfficialProductListProps) {
  const coveringOfficial = official.filter(
    (p) => p.covers && !p.is_county_context,
  );
  const contextAlerts = official.filter((p) => p.is_county_context || !p.covers);

  if (coveringOfficial.length === 0 && contextAlerts.length === 0) {
    return null;
  }

  return (
    <>
      {coveringOfficial.length > 0 && (
        <div className="space-y-1.5 text-xs">
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">
            Covering official products
          </h3>
          <ul className="space-y-1.5">
            {coveringOfficial.map((prod, idx) => (
              <li
                key={`${prod.code}-${String(idx)}`}
                className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40"
              >
                <div className="font-semibold text-slate-900 dark:text-slate-100">
                  {prod.code}
                  {prod.issuer ? ` · ${prod.issuer}` : ""}
                  {prod.storm_name
                    ? ` · ${prod.storm_name} (${prod.atcf_id ?? ""}, adv ${prod.advisory ?? "?"})`
                    : ""}
                </div>
                <div className="mt-0.5 text-slate-700 dark:text-slate-300">
                  {prod.reason}
                  {prod.distance_km !== null && prod.distance_km !== undefined
                    ? ` · ${formatKm(prod.distance_km)}`
                    : ""}
                </div>
                <div className="mt-0.5 text-slate-600 dark:text-slate-400">
                  Issued: {formatBothTimes(prod.issued_at, timeZone)}
                  {prod.expires_at
                    ? ` · Expires: ${formatBothTimes(prod.expires_at, timeZone)}`
                    : ""}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {contextAlerts.length > 0 && (
        <div className="space-y-1.5 text-xs">
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">
            County-zone alerts outside this location&apos;s zones (context
            only; never sets the level)
          </h3>
          <ul className="space-y-1.5">
            {contextAlerts.map((prod, idx) => (
              <li
                key={`${prod.code}-${String(idx)}`}
                className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/30"
              >
                <div className="font-semibold text-slate-800 dark:text-slate-200">
                  {prod.code}
                  {prod.issuer ? ` · ${prod.issuer}` : ""}
                </div>
                <div className="mt-0.5 text-slate-600 dark:text-slate-300">
                  {prod.reason}
                  {prod.zones.length > 0
                    ? ` · Zones: ${prod.zones.join(", ")}`
                    : ""}
                </div>
                <div className="mt-0.5 text-slate-500 dark:text-slate-400">
                  Issued: {formatBothTimes(prod.issued_at, timeZone)}
                  {prod.expires_at
                    ? ` · Expires: ${formatBothTimes(prod.expires_at, timeZone)}`
                    : ""}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
