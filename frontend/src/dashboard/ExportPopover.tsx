// frontend/src/dashboard/ExportPopover.tsx
import { Download } from "lucide-react";
import { Popover } from "radix-ui";
import { buttonClasses } from "../ui/Button.tsx";

export function buildReportHref(
  location: string | null,
  includeBriefing: boolean,
): string {
  const params = new URLSearchParams();
  if (location !== null) {
    params.set("location", location);
  }
  if (includeBriefing) {
    params.set("briefing", "true");
  }
  const query = params.toString();
  return query ? `/api/report?${query}` : "/api/report";
}

export interface ExportPopoverProps {
  readonly locationNames: readonly string[];
  readonly includeBriefing: boolean;
  readonly onIncludeBriefingChange: (nextChecked: boolean) => void;
}

export function ExportPopover({
  locationNames,
  includeBriefing,
  onIncludeBriefingChange,
}: ExportPopoverProps) {
  return (
    <Popover.Root modal={false}>
      <Popover.Trigger asChild>
        <button
          type="button"
          data-testid="export-report-trigger"
          className={buttonClasses("secondary", "sm", "lg:whitespace-nowrap")}
        >
          <Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>Export report</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          data-testid="export-report-popover"
          className="z-50 w-80 max-w-[calc(100vw-2rem)] rounded-card border border-line-strong bg-surface-raised p-4 text-sm text-ink shadow-raised focus:outline-hidden"
        >
          <p className="text-sm text-ink-muted">
            Export report saves a self-contained HTML file with each location’s
            threat level, deciding evidence, coarsened storm distance bands,
            8-point compass bearings, and whole-hour times (no coordinates or
            zone IDs); it opens offline anywhere and prints to PDF from the
            browser.
          </p>

          <label className="mt-3 flex cursor-pointer items-start gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={includeBriefing}
              onChange={(evt) => onIncludeBriefingChange(evt.target.checked)}
              className="mt-0.5 rounded border-line-strong text-brand focus:ring-brand"
            />
            <span>
              <span className="font-semibold">Include the AI briefing</span>{" "}
              <span className="text-ink-subtle">
                — its words quote NWS alerts and can name a county or a forecast
                office.
              </span>
            </span>
          </label>

          <div className="mt-3 space-y-1.5 border-t border-line pt-3">
            <a
              href={buildReportHref(null, includeBriefing)}
              download
              data-testid="export-report-all"
              className={buttonClasses("primary", "sm", "w-full justify-center")}
            >
              <Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>Download all locations</span>
            </a>

            {locationNames.map((name) => (
              <a
                key={name}
                href={buildReportHref(name, includeBriefing)}
                download
                data-testid={`export-report-${name}`}
                aria-label={`Export report for ${name}`}
                className={buttonClasses(
                  "secondary",
                  "sm",
                  "w-full justify-between",
                )}
              >
                <span className="truncate">{name}</span>
                <Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              </a>
            ))}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
