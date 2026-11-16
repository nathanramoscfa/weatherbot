// frontend/src/ui/Disclosure.tsx
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "./threat.ts";

export interface DisclosureProps {
  // The always-visible line ("Why this level / Official provenance & controls").
  readonly summary: ReactNode;
  // A short caption after the summary ("3 products, 2 evidence items").
  readonly caption?: ReactNode;
  readonly children: ReactNode;
  readonly className?: string;
  readonly id?: string;
  readonly "data-testid"?: string;
}

// Detail one click away: a native <details> and <summary>, closed by default.
// Native, because closed content stays in the DOM, needs no script, sets no
// inline style, is keyboard- and screen-reader-native, and prints; never a
// Radix collapsible (Phase 8 Decision 7). docs/DESIGN.md, "Disclosure".
export function Disclosure({
  summary,
  caption,
  children,
  className,
  id,
  "data-testid": testId,
}: DisclosureProps) {
  return (
    <details
      id={id}
      data-testid={testId}
      className={cx(
        "group rounded-card border border-line bg-surface-card",
        className,
      )}
    >
      <summary className="flex min-h-6 cursor-pointer list-none flex-wrap items-center gap-x-2 gap-y-0.5 rounded-card px-3.5 py-2.5 text-sm font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand [&::-webkit-details-marker]:hidden">
        <ChevronRight
          className="h-4 w-4 shrink-0 text-ink-subtle transition-transform group-open:rotate-90"
          aria-hidden="true"
        />
        <span>{summary}</span>
        {caption !== undefined && caption !== null && (
          <span className="text-caption font-normal text-ink-subtle">{caption}</span>
        )}
      </summary>
      <div className="space-y-3 border-t border-line px-3.5 py-3">{children}</div>
    </details>
  );
}
