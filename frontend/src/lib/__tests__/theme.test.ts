import { describe, expect, it } from "vitest";
import { applyTheme, resolveInitialTheme } from "../theme";

describe("resolveInitialTheme", () => {
  it("prefers a valid stored theme over everything else", () => {
    expect(resolveInitialTheme("sepia", "dark", true)).toBe("sepia");
  });

  it("ignores the legacy 'system' value and falls through to the cookie", () => {
    expect(resolveInitialTheme("system", "grey", true)).toBe("grey");
  });

  it("falls back to the mirror cookie when storage is empty", () => {
    expect(resolveInitialTheme(null, "dark", false)).toBe("dark");
  });

  it("resolves an unknown value against prefers-color-scheme", () => {
    expect(resolveInitialTheme("neon", null, true)).toBe("dark");
    expect(resolveInitialTheme("neon", "invalid", false)).toBe("light");
  });

  it("defaults to light when nothing is stored and the OS prefers light", () => {
    expect(resolveInitialTheme(null, null, false)).toBe("light");
  });

  it("resolves the OS preference exactly once (dark default)", () => {
    expect(resolveInitialTheme(null, null, true)).toBe("dark");
  });
});

describe("applyTheme", () => {
  it("sets the theme class on <html>, keeps 'dark' in sync, and mirrors storage + cookie", () => {
    document.documentElement.className = "";
    applyTheme("sepia");

    expect(document.documentElement.classList.contains("sepia")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("sepia");
    expect(document.cookie).toContain("theme=sepia");

    applyTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("sepia")).toBe(false);

    // Light clears every theme class.
    applyTheme("light");
    expect(document.documentElement.className.trim()).toBe("");

    localStorage.removeItem("theme");
    document.cookie = "theme=; max-age=0; path=/";
  });
});
