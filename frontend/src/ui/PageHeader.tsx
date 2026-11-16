// frontend/src/ui/PageHeader.tsx
import type { ReactNode } from "react";
import { cx } from "./threat.ts";

export interface PageHeaderProps {
  // The route's <h1>, which keeps today's name (AppShell.test.tsx finds each).
  readonly title: string;
  // The heading's id, for a section labelled by it.
  readonly titleId?: string;
  // One line saying what the page is for.
  readonly summary?: ReactNode;
  readonly actions?: ReactNode;
  // Keeps the heading for assistive technology but not on screen.
  readonly hideTitle?: boolean;
  readonly className?: string;
}

// The top of a route: its <h1>, a one-line summary, and an actions slot.
// docs/DESIGN.md, "PageHeader".
export function PageHeader({
  title,
  titleId,
  summary,
  actions,
  hideTitle = false,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cx(
        "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0 space-y-1">
        <h1
          id={titleId}
          className={
            hideTitle
              ? "sr-only"
              : "text-2xl font-semibold tracking-tight text-ink"
          }
        >
          {title}
        </h1>
        {summary !== undefined && summary !== null && (
          <p className="text-sm text-ink-subtle tabular-nums">{summary}</p>
        )}
      </div>
      {actions !== undefined && actions !== null && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      )}
    </header>
  );
}
