// frontend/src/app/ThreatLevelBadge.tsx
export type ThreatLevelNumber = 1 | 2 | 3 | 4 | 5;

export interface ThreatLevelDescriptor {
  readonly level: ThreatLevelNumber;
  readonly label: string;
  readonly badgeClassName: string;
}

export function describeThreatLevel(
  level: number,
  customLabel?: string,
): ThreatLevelDescriptor {
  switch (level) {
    case 5:
      return {
        level: 5,
        label: customLabel ?? "Hurricane Warning / Evacuation",
        badgeClassName:
          "border-red-700 bg-red-600 text-white dark:border-red-400 dark:bg-red-700 dark:text-white",
      };
    case 4:
      return {
        level: 4,
        label: customLabel ?? "Tropical Storm Warning / Hurricane Watch",
        badgeClassName:
          "border-orange-600 bg-orange-500 text-slate-950 dark:border-orange-400 dark:bg-orange-600 dark:text-white",
      };
    case 3:
      return {
        level: 3,
        label: customLabel ?? "Storm Watch",
        badgeClassName:
          "border-amber-500 bg-amber-300 text-slate-950 dark:border-amber-400 dark:bg-amber-500 dark:text-slate-950",
      };
    case 2:
      return {
        level: 2,
        label: customLabel ?? "Awareness",
        badgeClassName:
          "border-sky-600 bg-sky-100 text-sky-950 dark:border-sky-400 dark:bg-sky-900 dark:text-sky-100",
      };
    default:
      return {
        level: 1,
        label: customLabel ?? "All Clear",
        badgeClassName:
          "border-emerald-600 bg-emerald-100 text-emerald-950 dark:border-emerald-500 dark:bg-emerald-900 dark:text-emerald-100",
      };
  }
}

export interface ThreatLevelBadgeProps {
  readonly level: number;
  readonly label?: string;
  readonly atLeast?: boolean;
  readonly size?: "sm" | "md";
}

export function ThreatLevelBadge({
  level,
  label,
  atLeast = false,
  size = "md",
}: ThreatLevelBadgeProps) {
  const descriptor = describeThreatLevel(level, label);
  const sizeClass =
    size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border font-semibold ${sizeClass} ${descriptor.badgeClassName}`}
    >
      <span>
        {atLeast
          ? `At least Level ${String(descriptor.level)}`
          : `Level ${String(descriptor.level)}`}
      </span>
      <span aria-hidden="true">·</span>
      <span>{descriptor.label}</span>
    </span>
  );
}
