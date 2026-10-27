// frontend/src/app/theme.ts
export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "weatherbot.theme";

export function readStoredTheme(
  storage: Storage | undefined = globalThis.localStorage,
): ThemePreference {
  if (!storage) {
    return "system";
  }
  try {
    const raw = storage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") {
      return raw;
    }
  } catch {
    return "system";
  }
  return "system";
}

export function resolveIsDark(
  preference: ThemePreference,
  win: Window | undefined = globalThis.window,
): boolean {
  if (preference === "dark") {
    return true;
  }
  if (preference === "light") {
    return false;
  }
  if (win && typeof win.matchMedia === "function") {
    return win.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  return false;
}

export function applyThemePreference(
  preference: ThemePreference,
  doc: Document | undefined = globalThis.document,
  win: Window | undefined = globalThis.window,
): boolean {
  const isDark = resolveIsDark(preference, win);
  if (doc?.documentElement) {
    doc.documentElement.classList.toggle("dark", isDark);
  }
  return isDark;
}

export function persistAndApplyTheme(
  preference: ThemePreference,
  storage: Storage | undefined = globalThis.localStorage,
  doc: Document | undefined = globalThis.document,
  win: Window | undefined = globalThis.window,
): boolean {
  if (storage) {
    try {
      storage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // Ignore storage quota or private-mode restrictions.
    }
  }
  return applyThemePreference(preference, doc, win);
}
