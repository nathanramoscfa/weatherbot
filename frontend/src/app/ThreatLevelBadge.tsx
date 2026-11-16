// frontend/src/app/ThreatLevelBadge.tsx
export type ThreatLevelNumber = 1 | 2 | 3 | 4 | 5;

export interface ThreatLevelDescriptor {
  readonly level: ThreatLevelNumber;
  readonly label: string;
  readonly badgeClassName: string;
}

export interface ThreatLevelSvgClasses {
  readonly stroke: string;
  readonly fill: string;
}

export const LEVEL_SVG_CLASSES: Readonly<
  Record<ThreatLevelNumber, ThreatLevelSvgClasses>
> = {
  1: {
    stroke: "stroke-emerald-600 dark:stroke-emerald-400",
    fill: "fill-emerald-600 dark:fill-emerald-400",
  },
  2: {
    stroke: "stroke-sky-600 dark:stroke-sky-400",
    fill: "fill-sky-600 dark:fill-sky-400",
  },
  3: {
    stroke: "stroke-amber-500 dark:stroke-amber-400",
    fill: "fill-amber-500 dark:fill-amber-400",
  },
  4: {
    stroke: "stroke-orange-600 dark:stroke-orange-400",
    fill: "fill-orange-600 dark:fill-orange-400",
  },
  5: {
    stroke: "stroke-red-600 dark:stroke-red-400",
    fill: "fill-red-600 dark:fill-red-400",
  },
};

export function clampThreatLevel(level: number): ThreatLevelNumber {
  if (level >= 5) return 5;
  if (level === 4) return 4;
  if (level === 3) return 3;
  if (level === 2) return 2;
  return 1;
}

export function levelSvgClasses(level: number): ThreatLevelSvgClasses {
  switch (clampThreatLevel(level)) {
    case 5:
      return LEVEL_SVG_CLASSES[5];
    case 4:
      return LEVEL_SVG_CLASSES[4];
    case 3:
      return LEVEL_SVG_CLASSES[3];
    case 2:
      return LEVEL_SVG_CLASSES[2];
    default:
      return LEVEL_SVG_CLASSES[1];
  }
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
          "border-threat-5-accent bg-threat-5-accent text-threat-5-on-accent",
      };
    case 4:
      return {
        level: 4,
        label: customLabel ?? "Tropical Storm Warning / Hurricane Watch",
        badgeClassName:
          "border-threat-4-accent bg-threat-4-accent text-threat-4-on-accent",
      };
    case 3:
      return {
        level: 3,
        label: customLabel ?? "Storm Watch",
        badgeClassName:
          "border-threat-3-accent bg-threat-3-accent text-threat-3-on-accent",
      };
    case 2:
      return {
        level: 2,
        label: customLabel ?? "Awareness",
        badgeClassName:
          "border-threat-2-border bg-threat-2-surface text-threat-2-fg",
      };
    default:
      return {
        level: 1,
        label: customLabel ?? "All Clear",
        badgeClassName:
          "border-threat-1-border bg-threat-1-surface text-threat-1-fg",
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
    size === "sm" ? "px-2 py-0.5 text-caption" : "px-2.5 py-1 text-sm";
  return (
    <span
      className={`inline-flex flex-wrap items-center gap-x-1.5 rounded-md border font-semibold ${sizeClass} ${descriptor.badgeClassName}`}
    >
      <span className="whitespace-nowrap">
        {atLeast
          ? `At least Level ${String(descriptor.level)}`
          : `Level ${String(descriptor.level)}`}
      </span>
      <span aria-hidden="true">·</span>
      <span>{descriptor.label}</span>
    </span>
  );
}
