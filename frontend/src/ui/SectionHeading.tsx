// frontend/src/ui/SectionHeading.tsx
import type { ReactNode } from "react";
import { cx } from "./threat.ts";

export interface SectionHeadingProps {
  readonly as?: "h2" | "h3" | "h4";
  readonly id?: string;
  readonly children: ReactNode;
  // A sentence under the heading.
  readonly description?: ReactNode;
  readonly actions?: ReactNode;
  readonly className?: string;
}

function sizeClass(heading: "h2" | "h3" | "h4"): string {
  switch (heading) {
    case "h3":
      return "text-base font-semibold text-ink";
    case "h4":
      return "text-sm font-semibold text-ink";
    default:
      return "text-lg font-semibold text-ink";
  }
}

// A heading inside a page or card, with an optional description and actions.
// docs/DESIGN.md, "SectionHeading".
export function SectionHeading({
  as: Heading = "h2",
  id,
  children,
  description,
  actions,
  className,
}: SectionHeadingProps) {
  return (
    <div
      className={cx(
        "flex flex-wrap items-start justify-between gap-x-3 gap-y-2",
        className,
      )}
    >
      <div className="min-w-0 space-y-0.5">
        <Heading id={id} className={sizeClass(Heading)}>
          {children}
        </Heading>
        {description !== undefined && description !== null && (
          <p className="text-sm text-ink-subtle">{description}</p>
        )}
      </div>
      {actions !== undefined && actions !== null && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
