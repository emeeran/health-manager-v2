import { useState } from "react";
import { Check, Languages, Palette } from "lucide-react";
import { useI18n, LANGUAGES, type Language } from "../../lib/i18n";
import { applyTheme, THEMES, type Theme } from "../../lib/theme";
import { cn } from "../../lib/utils";

// Swatch previews use the literal palette values from globals.css so each
// option shows its own colours regardless of the theme currently applied.
const THEME_SWATCHES: Record<
  Theme,
  {
    key: "themeLight" | "themeSepia" | "themeGrey" | "themeDark";
    canvas: string;
    surface: string;
    ink: string;
  }
> = {
  light: {
    key: "themeLight",
    canvas: "#f7f8f9",
    surface: "#ffffff",
    ink: "#1c2530",
  },
  sepia: {
    key: "themeSepia",
    canvas: "#f4ecdc",
    surface: "#faf5ea",
    ink: "#33281a",
  },
  grey: {
    key: "themeGrey",
    canvas: "#d6d6d8",
    surface: "#e6e6e8",
    ink: "#101014",
  },
  dark: {
    key: "themeDark",
    canvas: "#191a1d",
    surface: "#212226",
    ink: "#f4f4f5",
  },
};

/** Read the theme the pre-paint bootstrap (or applyTheme) put on <html>. */
function readDocumentTheme(): Theme {
  const root = document.documentElement;
  if (root.classList.contains("dark")) return "dark";
  if (root.classList.contains("sepia")) return "sepia";
  if (root.classList.contains("grey")) return "grey";
  return "light";
}

/**
 * General settings: theme picker (four pinned themes) and language. The
 * chosen theme is pinned — the app never follows the OS appearance after the
 * first resolution.
 */
export function GeneralSection() {
  const { t, lang, setLang } = useI18n();
  // The anti-flash script in index.html has already applied the class before
  // this renders, so reading it lazily here shows the live theme.
  const [theme, setThemeState] = useState<Theme>(readDocumentTheme);

  function pickTheme(next: Theme) {
    setThemeState(next);
    applyTheme(next);
  }

  return (
    <section
      aria-label={t.settings.general.heading}
      className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Palette className="size-4 text-primary" aria-hidden />
        {t.settings.general.heading}
      </h2>

      <div className="space-y-1.5">
        <p className="text-sm font-medium">{t.settings.general.appearance}</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {THEMES.map((value) => {
            const swatch = THEME_SWATCHES[value];
            const selected = theme === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => pickTheme(value)}
                aria-pressed={selected}
                aria-label={t.settings.general[swatch.key]}
                className={cn(
                  "flex flex-col items-start gap-1.5 rounded-lg border p-2 text-xs font-medium transition-colors",
                  selected
                    ? "border-primary ring-1 ring-primary"
                    : "border-border hover:bg-muted/50",
                )}
              >
                <span
                  className="h-8 w-full rounded-md p-1 ring-1 ring-black/10"
                  style={{ backgroundColor: swatch.canvas }}
                >
                  <span
                    className="block h-3 w-3/4 rounded-sm"
                    style={{ backgroundColor: swatch.surface }}
                  />
                  <span
                    className="mt-1 block h-1 w-1/2 rounded-sm"
                    style={{ backgroundColor: swatch.ink, opacity: 0.4 }}
                  />
                </span>
                {t.settings.general[swatch.key]}
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-1.5">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Languages className="size-4 text-muted-foreground" aria-hidden />
          {t.settings.general.language}
        </p>
        <div className="flex flex-wrap gap-2">
          {LANGUAGES.map((option) => {
            const selected = lang === option.value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => setLang(option.value as Language)}
                aria-pressed={selected}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors",
                  selected
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border hover:bg-muted",
                )}
              >
                {selected && <Check className="size-3.5" aria-hidden />}
                {option.label}
              </button>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground">
          {t.settings.general.languageHint}
        </p>
      </div>
    </section>
  );
}
