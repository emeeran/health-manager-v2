import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NotificationBell } from "../notification-bell";

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

function renderBell() {
  return render(
    <SWRConfig value={{ provider: () => new Map() }}>
      <NotificationBell />
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NotificationBell", () => {
  it("shows the unread badge and the item list", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/notifications")
          ? {
              status: 200,
              body: {
                unread: 2,
                items: [
                  {
                    id: "n1",
                    title: "Refill soon",
                    body: "Metformin in 5 days",
                    read: false,
                    created_at: "2026-11-02T00:00:00Z",
                  },
                  {
                    id: "n2",
                    title: "Backup done",
                    body: "",
                    read: true,
                    created_at: "2026-11-01T00:00:00Z",
                  },
                ],
              },
            }
          : { status: 200, body: {} },
      ),
    );

    renderBell();

    const badge = await screen.findByTestId("unread-badge");
    expect(badge).toHaveTextContent("2");

    await userEvent.click(
      screen.getByRole("button", { name: /notifications/i }),
    );
    expect(await screen.findByText("Refill soon")).toBeInTheDocument();
    expect(screen.getByText("Metformin in 5 days")).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: /mark all read/i }),
    ).toBeInTheDocument();
  });

  it("marks one notification read", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/n1/read") && init?.method === "POST")
          return mockJsonResponse({ status: 200, body: { ok: true } });
        if (url.endsWith("/notifications"))
          return mockJsonResponse({
            status: 200,
            body: {
              unread: 1,
              items: [
                {
                  id: "n1",
                  title: "Refill soon",
                  body: "",
                  read: false,
                  created_at: "2026-11-02T00:00:00Z",
                },
              ],
            },
          });
        return mockJsonResponse({ status: 200, body: {} });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    renderBell();
    await userEvent.click(
      screen.getByRole("button", { name: /notifications/i }),
    );
    const item = await screen.findByRole("menuitem", { name: /refill soon/i });
    await userEvent.click(item);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) =>
          String(url).endsWith("/n1/read"),
        ),
      ).toHaveLength(1),
    );
  });

  it("renders no badge without unread items", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/notifications")
          ? { status: 200, body: { unread: 0, items: [] } }
          : { status: 200, body: {} },
      ),
    );

    renderBell();
    await waitFor(() =>
      expect(screen.queryByTestId("unread-badge")).not.toBeInTheDocument(),
    );
  });
});
