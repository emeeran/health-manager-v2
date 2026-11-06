import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../lib/api-client";
import AppLayout from "../../layouts/AppLayout";
import Home from "../home";

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
  handler: (url: string, init?: RequestInit) => MockResponseInit,
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    mockJsonResponse(handler(String(input), init)),
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
      <MemoryRouter initialEntries={["/"]}>{ui}</MemoryRouter>
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("smoke", () => {
  it("renders AppLayout without crashing", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/auth/me")
          ? { status: 200, body: { id: "u1", username: "test", role: "admin" } }
          : { status: 200, body: [] },
      ),
    );

    renderWithProviders(<AppLayout />);

    expect(screen.getByText("Family Health Manager")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /members/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /chat/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
    await screen.findByText("test"); // /auth/me resolved into the header
  });

  it("renders the Home page", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/dashboard")
          ? {
              status: 200,
              body: {
                household_name: "Test family",
                alerts: [],
                scores: [],
                members: [],
              },
            }
          : { status: 200, body: [] },
      ),
    );

    renderWithProviders(<Home />);

    expect(
      await screen.findByRole("heading", { name: /Test family/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Quick actions" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Smart entry")).toBeInTheDocument();
  });
});

describe("api client auth refresh", () => {
  it("performs a single-flight refresh and retries once on 401", async () => {
    const fetchMock = makeFetchMock((url) => {
      if (url.endsWith("/auth/refresh")) return { status: 204 };
      if (url.endsWith("/things"))
        return { status: 401, body: { detail: "token expired" } };
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/things")).rejects.toThrow("token expired");

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/auth/refresh"),
      ),
    ).toHaveLength(1);
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/things"),
      ),
    ).toHaveLength(2);
  });

  it("does not refresh for /auth/ paths", async () => {
    const fetchMock = makeFetchMock((url) => {
      if (url.endsWith("/auth/login"))
        return { status: 401, body: { detail: "bad credentials" } };
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/auth/login", { method: "POST" })).rejects.toThrow(
      "bad credentials",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
