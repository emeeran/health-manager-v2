import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HouseholdSection } from "../household-section";

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

function renderSection() {
  return render(
    <SWRConfig value={{ provider: () => new Map() }}>
      <HouseholdSection />
    </SWRConfig>,
  );
}

const ADMIN = {
  id: "h1",
  name: "Test Household",
  my_role: "admin",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HouseholdSection", () => {
  it("shows members with roles for admins", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) => {
        if (url.endsWith("/household")) return { status: 200, body: ADMIN };
        if (url.endsWith("/household/users"))
          return {
            status: 200,
            body: [
              {
                user_id: "u1",
                username: "owner",
                role: "admin",
                is_primary: true,
                created_at: "2026-01-01T00:00:00Z",
              },
              {
                user_id: "u2",
                username: "nurse",
                role: "viewer",
                is_primary: false,
                created_at: "2026-01-02T00:00:00Z",
              },
            ],
          };
        if (url.includes("/invitations")) return { status: 200, body: [] };
        return { status: 200, body: {} };
      }),
    );

    renderSection();

    await screen.findByText("nurse");
    expect(screen.getByLabelText("Role for nurse")).toHaveValue("viewer");
    expect(screen.getByLabelText("Role for owner")).toBeDisabled(); // owner locked
  });

  it("hides member management from non-admins", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/household")
          ? { status: 200, body: { ...ADMIN, my_role: "viewer" } }
          : { status: 200, body: [] },
      ),
    );

    renderSection();

    await screen.findByText(/Household · viewer/i);
    expect(screen.queryByText("Members")).not.toBeInTheDocument();
    expect(screen.queryByText("Invitations")).not.toBeInTheDocument();
  });

  it("creates an invitation and shows the token once", async () => {
    const user = userEvent.setup();
    const fetchMock = makeFetchMock((url, init) => {
      if (url.endsWith("/household")) return { status: 200, body: ADMIN };
      if (url.endsWith("/household/users")) return { status: 200, body: [] };
      if (url.endsWith("/invitations") && init?.method === "POST")
        return {
          status: 201,
          body: {
            id: "i1",
            token: "one-time-token-abc",
            role: "member",
            expires_at: "2026-12-01T00:00:00Z",
          },
        };
      if (url.includes("/invitations")) return { status: 200, body: [] };
      return { status: 200, body: {} };
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSection();
    await screen.findByText("Invitations");

    await user.click(screen.getByRole("button", { name: /create invite/i }));

    await waitFor(() =>
      expect(screen.getByText(/one-time-token-abc/)).toBeInTheDocument(),
    );
    const call = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith("/invitations") && init?.method === "POST",
    );
    expect(JSON.parse(String(call![1]!.body))).toEqual({ role: "member" });
  });
});
