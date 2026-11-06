import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../lib/api-client";
import Hub from "../ai-tools/hub";

interface MockResponseInit {
  status: number;
  body?: unknown;
}

function mockJsonResponse({ status, body }: MockResponseInit) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  };
}

function makeFetchMock(
  handler: (url: string) => MockResponseInit,
): ReturnType<typeof vi.fn> {
  return vi.fn(async (input: RequestInfo | URL) =>
    mockJsonResponse(handler(String(input))),
  );
}

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <SWRConfig
      value={{
        fetcher: (key) => apiRequest(String(key)),
        provider: () => new Map(),
      }}
    >
      <MemoryRouter initialEntries={["/ai-tools"]}>{ui}</MemoryRouter>
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AiToolsHub", () => {
  it("renders the grouped card grid linking every tool page", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/members")
          ? {
              status: 200,
              body: [{ id: "m-1", name: "Amma", relationship: "self" }],
            }
          : { status: 200, body: [] },
      ),
    );

    renderWithProviders(<Hub />);

    expect(
      await screen.findByRole("heading", { name: /AI tools/i }),
    ).toBeInTheDocument();
    // Group headings render in order.
    expect(screen.getByRole("region", { name: "Reports" })).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Medicine reports" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Tools" })).toBeInTheDocument();
    // Cards link to the tool pages; no member pinned → plain paths.
    expect(
      screen.getByRole("link", { name: /Health insights/i }),
    ).toHaveAttribute("href", "/ai-tools/health-insights");
    expect(
      screen.getByRole("link", { name: /Quick health summary/i }),
    ).toHaveAttribute("href", "/ai-tools/smart-report");
    expect(
      screen.getByRole("link", { name: /Drug interactions/i }),
    ).toHaveAttribute("href", "/ai-tools/drug-interactions");
    expect(
      screen.getByRole("link", { name: /any two medicines/i }),
    ).toHaveAttribute("href", "/ai-tools/drug-interaction-pair");
    expect(
      screen.getByRole("link", { name: /Price comparison/i }),
    ).toHaveAttribute("href", "/ai-tools/price-comparison");
    expect(
      screen.getByRole("link", { name: /Doctor visit summary/i }),
    ).toHaveAttribute("href", "/ai-tools/visit-summary");
  });

  it("shows the empty state when the household has no members", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock(() => ({ status: 200, body: [] })),
    );

    renderWithProviders(<Hub />);

    expect(
      await screen.findByText(/No family members yet/i),
    ).toBeInTheDocument();
  });
});
