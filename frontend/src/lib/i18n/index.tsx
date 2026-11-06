import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { en, type Dictionary } from "./en";
import { hi } from "./hi";
import { pt } from "./pt";
import { ta } from "./ta";

export type Language = "en" | "pt" | "ta" | "hi";

export const LANGUAGES: readonly { value: Language; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ta", label: "தமிழ்" },
  { value: "hi", label: "हिन्दी" },
  { value: "pt", label: "Português" },
];

const LANG_STORAGE_KEY = "lang";
const LANG_COOKIE_KEY = "lang";

const DICTIONARIES: Record<Language, Dictionary> = { en, pt, ta, hi };

function isLanguage(value: string | null): value is Language {
  return value === "en" || value === "pt" || value === "ta" || value === "hi";
}

/** Pure resolver: localStorage → mirror cookie → navigator language → "en". */
export function resolveInitialLanguage(
  storage: string | null,
  cookie: string | null,
  navigatorLanguage: string,
): Language {
  if (isLanguage(storage)) return storage;
  if (isLanguage(cookie)) return cookie;
  const nav = navigatorLanguage.toLowerCase();
  if (nav.startsWith("pt")) return "pt";
  if (nav.startsWith("ta")) return "ta";
  if (nav.startsWith("hi")) return "hi";
  return "en";
}

function readLangCookie(): string | null {
  try {
    const match = document.cookie.match(/(?:^|; )lang=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
}

function getInitialLanguage(): Language {
  let storage: string | null = null;
  try {
    storage = localStorage.getItem(LANG_STORAGE_KEY);
  } catch {
    // Storage unavailable — fall through to the cookie / navigator.
  }
  return resolveInitialLanguage(
    storage,
    readLangCookie(),
    typeof navigator !== "undefined" ? navigator.language : "en",
  );
}

interface I18nContextValue {
  lang: Language;
  setLang: (lang: Language) => void;
  /** Dictionary for the active language (typed against en.ts). */
  t: Dictionary;
}

const I18nContext = createContext<I18nContextValue | null>(null);

/**
 * Language selection works like the theme: persisted to localStorage and
 * mirrored into a cookie so the Tauri WebKitGTK webview (which can lose
 * localStorage across restarts) keeps the choice.
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>(getInitialLanguage);

  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      setLang: (next: Language) => {
        setLangState(next);
        try {
          localStorage.setItem(LANG_STORAGE_KEY, next);
        } catch {
          // Non-fatal: cookie mirror below still covers WebKitGTK.
        }
        document.cookie = `${LANG_COOKIE_KEY}=${next}; max-age=31536000; path=/; SameSite=Strict`;
      },
      t: DICTIONARIES[lang],
    }),
    [lang],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}
