// frontend/public/theme-init.js
(function applyInitialTheme() {
  let stored;
  try {
    stored = window.localStorage.getItem("weatherbot.theme");
  } catch {
    stored = null;
  }
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark =
    stored === "dark" || ((stored === null || stored === "system") && prefersDark);
  const root = document.documentElement;
  if (isDark) {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
})();
