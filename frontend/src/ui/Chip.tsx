// frontend/src/ui/Chip.tsx
import type { HTMLAttributes, ReactNode } from "react";
import { cx, threatClasses } from "./threat.ts";

export type ChipTone = "neutral" | "brand" | "ai" | "warning";

export interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  readonly tone?: ChipTone;
  // Tints the chip with a threat level instead of a tone (1 to 5).
  readonly level?: number | null;
  readonly icon?: ReactNode;
  readonly children: ReactNode;
}

function toneClass(tone: ChipTone): string {
  switch (tone) {
    case "brand":
      return "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-100";
    case "ai":
      return "border-violet-200 bg-violet-50 text-violet-900 dark:border-violet-800 dark:bg-violet-950/60 dark:text-violet-100";
    case "warning":
      return "border-amber-400 bg-amber-50 text-amber-950 dark:border-amber-600 dark:bg-amber-950/60 dark:text-amber-100";
    default:
      return "border-line bg-surface-inset text-ink-muted";
  }
}

// A short label: a code, a count, a state. Its text is a caption, so it is a
// <span>, never a paragraph. docs/DESIGN.md, "Chip".
export function Chip({
  tone = "neutral",
  level = null,
  icon,
  children,
  className,
  ...rest
}: ChipProps) {
  return (
    <span
      {...rest}
      className={cx(
        "inline-flex items-center gap-1 rounded-pill border px-2 py-0.5 text-caption font-medium",
        level === null ? toneClass(tone) : threatClasses(level).tint,
        className,
      )}
    >
      {icon}
      <span>{children}</span>
    </span>
  );
}
