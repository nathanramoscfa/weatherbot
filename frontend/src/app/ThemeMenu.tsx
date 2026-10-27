// frontend/src/app/ThemeMenu.tsx
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import { useEffect, useState } from "react";
import {
  applyThemePreference,
  persistAndApplyTheme,
  readStoredTheme,
  type ThemePreference,
} from "./theme.ts";

const THEME_OPTIONS: readonly {
  readonly value: ThemePreference;
  readonly label: string;
}[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function ThemeMenu() {
  const [theme, setTheme] = useState<ThemePreference>(() => readStoredTheme());

  useEffect(() => {
    applyThemePreference(theme);
    if (
      theme !== "system" ||
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    ) {
      return undefined;
    }
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => {
      applyThemePreference("system");
    };
    mediaQuery.addEventListener("change", handleChange);
    return () => {
      mediaQuery.removeEventListener("change", handleChange);
    };
  }, [theme]);

  const handleValueChange = (nextValue: string) => {
    if (
      nextValue === "system" ||
      nextValue === "light" ||
      nextValue === "dark"
    ) {
      setTheme(nextValue);
      persistAndApplyTheme(nextValue);
    }
  };

  const currentLabel =
    theme === "dark" ? "Dark" : theme === "light" ? "Light" : "System";

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label={`Theme: ${currentLabel}`}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-800 shadow-xs hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
        >
          {theme === "dark" ? (
            <Moon className="h-3.5 w-3.5" aria-hidden="true" />
          ) : theme === "light" ? (
            <Sun className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Monitor className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          <span>Theme: {currentLabel}</span>
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 min-w-36 rounded-md border border-slate-200 bg-white p-1 text-slate-900 shadow-md dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          <DropdownMenu.RadioGroup
            value={theme}
            onValueChange={handleValueChange}
            aria-label="Color theme"
          >
            {THEME_OPTIONS.map((option) => (
              <DropdownMenu.RadioItem
                key={option.value}
                value={option.value}
                className="flex cursor-pointer items-center justify-between rounded-sm px-2.5 py-1.5 text-xs outline-hidden select-none focus:bg-slate-100 data-[highlighted]:bg-slate-100 dark:focus:bg-slate-800 dark:data-[highlighted]:bg-slate-800"
              >
                <span>{option.label}</span>
                <DropdownMenu.ItemIndicator>
                  <Check className="h-3.5 w-3.5" aria-hidden="true" />
                </DropdownMenu.ItemIndicator>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
