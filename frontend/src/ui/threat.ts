// frontend/src/ui/threat.ts
import {
  clampThreatLevel,
  type ThreatLevelNumber,
} from "../app/ThreatLevelBadge.tsx";

// The threat palette's classes, spelled out per level so Tailwind's scanner
// finds every one (docs/DESIGN.md, "Tokens"). `tint` is a card or callout on
// the level's surface; `solid` is the level's accent carrying its own text.
export interface ThreatClasses {
  readonly tint: string;
  readonly solid: string;
  readonly fg: string;
}

export const THREAT_CLASSES: Readonly<Record<ThreatLevelNumber, ThreatClasses>> =
  {
    1: {
      tint: "border-threat-1-border bg-threat-1-surface text-threat-1-fg",
      solid: "border-threat-1-accent bg-threat-1-accent text-threat-1-on-accent",
      fg: "text-threat-1-fg",
    },
    2: {
      tint: "border-threat-2-border bg-threat-2-surface text-threat-2-fg",
      solid: "border-threat-2-accent bg-threat-2-accent text-threat-2-on-accent",
      fg: "text-threat-2-fg",
    },
    3: {
      tint: "border-threat-3-border bg-threat-3-surface text-threat-3-fg",
      solid: "border-threat-3-accent bg-threat-3-accent text-threat-3-on-accent",
      fg: "text-threat-3-fg",
    },
    4: {
      tint: "border-threat-4-border bg-threat-4-surface text-threat-4-fg",
      solid: "border-threat-4-accent bg-threat-4-accent text-threat-4-on-accent",
      fg: "text-threat-4-fg",
    },
    5: {
      tint: "border-threat-5-border bg-threat-5-surface text-threat-5-fg",
      solid: "border-threat-5-accent bg-threat-5-accent text-threat-5-on-accent",
      fg: "text-threat-5-fg",
    },
  };

export function threatClasses(level: number): ThreatClasses {
  return THREAT_CLASSES[clampThreatLevel(level)];
}

// Joins class names, dropping empty and false entries.
export function cx(...parts: readonly (string | false | null | undefined)[]): string {
  return parts.filter((part) => typeof part === "string" && part.length > 0).join(" ");
}
