// frontend/src/ui/Callout.tsx
import { CircleAlert, Info, StickyNote, TriangleAlert } from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "./threat.ts";

export type CalloutTone = "note" | "warning" | "error" | "info";
export type CalloutRole = "note" | "alert" | "status" | "none";

export interface CalloutProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "role" | "title"> {
  readonly tone: CalloutTone;
  // The landmark role, as each existing use already has; `none` sets no role.
  readonly role?: CalloutRole;
  readonly title?: ReactNode;
  readonly children?: ReactNode;
}

// Each tone's usual role: a note is a note, information is a polite status,
// and warnings and errors are alerts. A use that had another keeps it.
export const DEFAULT_CALLOUT_ROLE: Readonly<Record<CalloutTone, CalloutRole>> = {
  note: "note",
  info: "status",
  warning: "alert",
  error: "alert",
};

// Each tone's box, icon colour, and icon.
function toneParts(tone: CalloutTone) {
  switch (tone) {
    case "info":
      return {
        box: "border-sky-300 bg-sky-50 text-sky-950 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-100",
        icon: "text-sky-700 dark:text-sky-300",
        Icon: Info,
      };
    case "warning":
      return {
        box: "border-amber-400 bg-amber-50 text-amber-950 dark:border-amber-600 dark:bg-amber-950/60 dark:text-amber-100",
        icon: "text-amber-700 dark:text-amber-300",
        Icon: TriangleAlert,
      };
    case "error":
      return {
        box: "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-100",
        icon: "text-red-700 dark:text-red-300",
        Icon: CircleAlert,
      };
    default:
      return {
        box: "border-line bg-surface-inset text-ink-muted",
        icon: "text-ink-subtle",
        Icon: StickyNote,
      };
  }
}

function defaultRole(tone: CalloutTone): CalloutRole {
  switch (tone) {
    case "info":
      return DEFAULT_CALLOUT_ROLE.info;
    case "warning":
      return DEFAULT_CALLOUT_ROLE.warning;
    case "error":
      return DEFAULT_CALLOUT_ROLE.error;
    default:
      return DEFAULT_CALLOUT_ROLE.note;
  }
}

// A boxed message beside the content it concerns. docs/DESIGN.md, "Callout".
export function Callout({
  tone,
  role = defaultRole(tone),
  title,
  children,
  className,
  ...rest
}: CalloutProps) {
  const { box, icon, Icon } = toneParts(tone);
  return (
    <div
      {...rest}
      role={role === "none" ? undefined : role}
      className={cx(
        "flex items-start gap-2.5 rounded-card border px-3.5 py-2.5 text-sm",
        box,
        className,
      )}
    >
      <Icon className={cx("mt-0.5 h-4 w-4 shrink-0", icon)} aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-1">
        {title !== undefined && title !== null && (
          <span className="block font-semibold">{title}</span>
        )}
        {children}
      </div>
    </div>
  );
}
