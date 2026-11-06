import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { I18nProvider, resolveInitialLanguage, useI18n } from "../index";

function Probe() {
  const { t, lang, setLang } = useI18n();
  return (
    <div>
      <p data-testid="lang">{lang}</p>
      <p data-testid="nav-members">{t.nav.members}</p>
      <p data-testid="settings-title">{t.settings.title}</p>
      <button type="button" onClick={() => setLang("pt")}>
        switch
      </button>
    </div>
  );
}

function readCookie(key: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${key}=([^;]*)`));
  return match ? match[1] : null;
}

afterEach(() => {
  localStorage.clear();
  document.cookie = "lang=; max-age=0; path=/";
});

describe("useI18n", () => {
  it("defaults to English and exposes the typed dictionary", () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );

    expect(screen.getByTestId("lang")).toHaveTextContent("en");
    expect(screen.getByTestId("nav-members")).toHaveTextContent("Members");
    expect(screen.getByTestId("settings-title")).toHaveTextContent("Settings");
  });

  it("switches to the pilot Portuguese dictionary and persists the choice", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: "switch" }));

    expect(screen.getByTestId("lang")).toHaveTextContent("pt");
    expect(screen.getByTestId("nav-members")).toHaveTextContent("Membros");
    expect(screen.getByTestId("settings-title")).toHaveTextContent(
      "Configurações",
    );
    expect(localStorage.getItem("lang")).toBe("pt");
    expect(readCookie("lang")).toBe("pt");
  });

  it("restores a persisted choice from localStorage", () => {
    localStorage.setItem("lang", "pt");
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );

    expect(screen.getByTestId("nav-members")).toHaveTextContent("Membros");
  });
});

describe("resolveInitialLanguage", () => {
  it("prefers storage, then the mirror cookie, then the browser language", () => {
    expect(resolveInitialLanguage("pt", "en", "en-GB")).toBe("pt");
    expect(resolveInitialLanguage(null, "pt", "en-GB")).toBe("pt");
    expect(resolveInitialLanguage(null, null, "pt-BR")).toBe("pt");
    expect(resolveInitialLanguage(null, null, "en-GB")).toBe("en");
    expect(resolveInitialLanguage("fr", null, "en-GB")).toBe("en");
  });

  it("resolves Tamil and Hindi from storage, cookie, or browser language", () => {
    expect(resolveInitialLanguage("ta", null, "en-GB")).toBe("ta");
    expect(resolveInitialLanguage(null, "hi", "en-GB")).toBe("hi");
    expect(resolveInitialLanguage(null, null, "ta-IN")).toBe("ta");
    expect(resolveInitialLanguage(null, null, "hi-IN")).toBe("hi");
    expect(resolveInitialLanguage(null, null, "en-GB")).toBe("en");
  });

  it("exposes the Tamil and Hindi dictionaries with matching keys", () => {
    // Dictionary key parity is enforced by the Dictionary type; this checks
    // the values render for both new locales. One render per locale — the
    // provider reads storage once at mount.
    for (const [lang, navMembers, title] of [
      ["ta", "உறுப்பினர்கள்", "அமைப்புகள்"],
      ["hi", "सदस्य", "सेटिंग्स"],
    ] as const) {
      localStorage.setItem("lang", lang);
      render(
        <I18nProvider>
          <Probe />
        </I18nProvider>,
      );
      expect(screen.getByTestId("nav-members")).toHaveTextContent(navMembers);
      expect(screen.getByTestId("settings-title")).toHaveTextContent(title);
      cleanup();
    }
  });
});
