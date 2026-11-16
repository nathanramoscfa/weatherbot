// frontend/src/ui/Card.tsx
import type { HTMLAttributes, ReactNode } from "react";
import { cx, threatClasses } from "./threat.ts";

export type CardElevation = "flat" | "card" | "raised";
export type CardPadding = "none" | "sm" | "md";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  readonly as?: "section" | "article" | "div" | "aside" | "figure";
  // Tints the card with a threat level's surface and border (1 to 5).
  readonly level?: number | null;
  readonly elevation?: CardElevation;
  readonly padding?: CardPadding;
  readonly children?: ReactNode;
}

function elevationClass(elevation: CardElevation): string {
  switch (elevation) {
    case "flat":
      return "";
    case "raised":
      return "shadow-raised";
    default:
      return "shadow-card";
  }
}

function paddingClass(padding: CardPadding): string {
  switch (padding) {
    case "none":
      return "";
    case "sm":
      return "p-3";
    default:
      return "p-4 sm:p-5";
  }
}

// A surface that groups one subject: the neutral card, or with `level` the
// threat level's tint. docs/DESIGN.md, "Card".
export function Card({
  as: Element = "section",
  level = null,
  elevation = "card",
  padding = "md",
  className,
  children,
  ...rest
}: CardProps) {
  const surface =
    level === null
      ? "border-line bg-surface-card text-ink"
      : threatClasses(level).tint;
  return (
    <Element
      {...rest}
      className={cx(
        "rounded-card border",
        surface,
        elevationClass(elevation),
        paddingClass(padding),
        className,
      )}
    >
      {children}
    </Element>
  );
}
