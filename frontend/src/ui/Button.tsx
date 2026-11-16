// frontend/src/ui/Button.tsx
import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  ReactNode,
  Ref,
} from "react";
import { Link } from "react-router";
import { cx } from "./threat.ts";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

// Shared by Button and LinkButton: a visible focus ring and a target of at
// least 24 by 24 CSS pixels (WCAG 2.2, 2.5.8). docs/DESIGN.md, "Button".
const BASE =
  "inline-flex min-h-6 min-w-6 items-center justify-center gap-1.5 rounded-control border font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60";

export const BUTTON_VARIANTS: Readonly<Record<ButtonVariant, string>> = {
  primary: "border-brand bg-brand text-on-brand hover:border-brand-hover hover:bg-brand-hover",
  secondary:
    "border-line-strong bg-surface-card text-ink hover:bg-surface-inset",
  ghost: "border-transparent bg-transparent text-ink-muted hover:bg-surface-inset hover:text-ink",
  danger:
    "border-red-700 bg-red-700 text-white hover:border-red-800 hover:bg-red-800 dark:border-red-400 dark:bg-red-400 dark:text-slate-950 dark:hover:border-red-300 dark:hover:bg-red-300",
};

export const BUTTON_SIZES: Readonly<Record<ButtonSize, string>> = {
  sm: "px-2.5 py-1 text-sm",
  md: "px-3.5 py-2 text-sm",
};

function variantClass(variant: ButtonVariant): string {
  switch (variant) {
    case "primary":
      return BUTTON_VARIANTS.primary;
    case "ghost":
      return BUTTON_VARIANTS.ghost;
    case "danger":
      return BUTTON_VARIANTS.danger;
    default:
      return BUTTON_VARIANTS.secondary;
  }
}

export function buttonClasses(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "sm",
  className?: string,
): string {
  return cx(
    BASE,
    variantClass(variant),
    size === "md" ? BUTTON_SIZES.md : BUTTON_SIZES.sm,
    className,
  );
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly ref?: Ref<HTMLButtonElement>;
  readonly children?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "sm",
  type = "button",
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={buttonClasses(variant, size, className)}
    >
      {children}
    </button>
  );
}

interface LinkButtonBase
  extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly children?: ReactNode;
}

// A link that looks like a button: `to` routes inside the app, `href` is a
// plain link (a download, an attachment).
export type LinkButtonProps = LinkButtonBase &
  (
    | { readonly to: string; readonly href?: never }
    | { readonly href: string; readonly to?: never }
  );

export function LinkButton({
  variant = "secondary",
  size = "sm",
  className,
  children,
  to,
  href,
  ...rest
}: LinkButtonProps) {
  const classes = buttonClasses(variant, size, className);
  if (to !== undefined) {
    return (
      <Link {...rest} to={to} className={classes}>
        {children}
      </Link>
    );
  }
  return (
    <a {...rest} href={href} className={classes}>
      {children}
    </a>
  );
}
