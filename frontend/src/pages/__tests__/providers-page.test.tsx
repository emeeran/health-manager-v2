import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../lib/api-client";
import Providers from "../providers";

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

function renderPage() {
  return render(
    <SWRConfig
      value={{
        fetcher: (key) => apiRequest(String(key)),
        provider: () => new Map(),
      }}
    >
      <Providers />
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Providers page", () => {
  it("renders the directory and adds a provider", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/providers") && init?.method === "POST")
          return mockJsonResponse({
            status: 201,
            body: {
              id: "p1",
              name: "Dr Priya Rao",
              specialty: "Cardiology",
              hospital: "City Hosp",
              phone: null,
              notes: null,
              created_at: "2026-11-02T00:00:00Z",
            },
          });
        if (url.endsWith("/providers"))
          return mockJsonResponse({
            status: 200,
            body: [
              {
                id: "p1",
                name: "Dr Priya Rao",
                specialty: "Cardiology",
                hospital: "City Hosp",
                phone: null,
                notes: null,
                created_at: "2026-11-02T00:00:00Z",
              },
            ],
          });
        return mockJsonResponse({ status: 200, body: {} });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    await screen.findByText("Dr Priya Rao");
    expect(screen.getByText("Cardiology")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Name", { exact: true }), "Dr New");
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(
          ([url, init]) =>
            String(url).endsWith("/providers") && init?.method === "POST",
        ),
      ).toHaveLength(1),
    );
    const body = JSON.parse(
      String(
        fetchMock.mock.calls.find(
          ([url, init]) =>
            String(url).endsWith("/providers") && init?.method === "POST",
        )![1]!.body,
      ),
    );
    expect(body.name).toBe("Dr New");
  });

  it("shows the empty state without providers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockJsonResponse({ status: 200, body: [] })),
    );

    renderPage();

    await screen.findByText("No providers yet");
  });
});
