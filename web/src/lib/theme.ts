export type ThemeId = "day" | "night" | "reading";

export const THEME_KEY = "jarvis-theme";

export function parseTheme(raw: string | null | undefined): ThemeId {
  if (raw === "night" || raw === "reading" || raw === "day") return raw;
  return "day";
}

export function themeClass(theme: ThemeId): "light" | "dark" {
  return theme === "night" ? "dark" : "light";
}

export function readTheme(): ThemeId {
  if (typeof localStorage === "undefined") return "day";
  return parseTheme(localStorage.getItem(THEME_KEY));
}

export function applyTheme(theme: ThemeId) {
  const root = document.documentElement;
  root.classList.toggle("dark", themeClass(theme) === "dark");
  root.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
}
