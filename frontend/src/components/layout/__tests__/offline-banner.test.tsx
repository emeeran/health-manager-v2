import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../../lib/i18n";
import { OfflineBanner } from "../offline-banner";

function renderBanner() {
  return render(
    <I18nProvider>
      <OfflineBanner />
    </I18nProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OfflineBanner", () => {
  it("is hidden while online", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the cached-data banner when offline", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    renderBanner();
    expect(screen.getByRole("status")).toHaveTextContent(
      /Offline — showing cached data/i,
    );
  });

  it("toggles with the browser online/offline events", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();

    fireEvent(window, new Event("offline"));
    expect(screen.getByRole("status")).toHaveTextContent(/Offline/i);

    fireEvent(window, new Event("online"));
    expect(container).toBeEmptyDOMElement();
  });

  it("uses the Portuguese dictionary when pt is selected", () => {
    localStorage.setItem("lang", "pt");
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    renderBanner();
    expect(screen.getByRole("status")).toHaveTextContent(/Sem ligação/i);
    localStorage.removeItem("lang");
  });
});
