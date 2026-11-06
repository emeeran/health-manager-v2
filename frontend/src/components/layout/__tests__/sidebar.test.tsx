import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { I18nProvider } from "../../../lib/i18n";
import { Sidebar } from "../sidebar";

function renderSidebar() {
  return render(
    <MemoryRouter>
      <I18nProvider>
        <Sidebar />
      </I18nProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("Sidebar — collapse toggle", () => {
  it("starts expanded with labels visible", () => {
    renderSidebar();
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Collapse sidebar" }),
    ).toHaveAttribute("aria-expanded", "true");
  });

  it("collapses to icon-only, hides labels, and persists the state", () => {
    renderSidebar();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    // Labels gone; icon-only NavLinks keep an accessible name via aria-label.
    expect(screen.queryByText("Home")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(localStorage.getItem("sidebar-collapsed")).toBe("1");
  });

  it("reopens collapsed when the persisted state says so", () => {
    localStorage.setItem("sidebar-collapsed", "1");
    renderSidebar();
    expect(screen.queryByText("Home")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toBeInTheDocument();
  });

  it("defaults to the icon rail on narrow viewports instead of hiding", () => {
    // Sub-md windows previously lost the sidebar entirely (`hidden md:flex`)
    // — tiled or HiDPI-scaled desktop windows had no navigation at all.
    Object.defineProperty(window, "innerWidth", {
      value: 640,
      configurable: true,
    });
    try {
      renderSidebar();
      expect(screen.queryByText("Home")).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Expand sidebar" }),
      ).toBeInTheDocument();
    } finally {
      Object.defineProperty(window, "innerWidth", {
        value: 1024,
        configurable: true,
      });
    }
  });
});
