import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../lib/api-client";
import Members from "../members";

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
      <Members />
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Members page — onboarding form", () => {
  it("creates a member from the minimal fields, no history inputs", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/members") && init?.method === "POST")
          return mockJsonResponse({
            status: 201,
            body: {
              id: "m1",
              name: "Asha",
              relationship: "self",
              birth_date: null,
              sex: null,
              phone: null,
              address: null,
              medical_history: null,
              family_medical_history: null,
              current_medications: null,
              blood_group: null,
              emergency_contact_name: null,
              emergency_contact_phone: null,
              notes: null,
              created_at: "2026-11-04T00:00:00Z",
            },
          });
        if (url.endsWith("/members"))
          return mockJsonResponse({ status: 200, body: [] });
        return mockJsonResponse({ status: 200, body: {} });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    await user.type(screen.getByLabelText("Full name"), "Asha");
    // Medical / family histories belong to the profile (edit) form only —
    // the quick-add form must not offer them.
    expect(
      screen.queryByPlaceholderText(/Conditions, surgeries/),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^add member$/i }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(
          ([url, init]) =>
            String(url).endsWith("/members") && init?.method === "POST",
        ),
      ).toHaveLength(1);
    });
    const body = JSON.parse(
      String(
        fetchMock.mock.calls.find(
          ([url, init]) =>
            String(url).endsWith("/members") && init?.method === "POST",
        )![1]!.body,
      ),
    );
    expect(body.name).toBe("Asha");
    expect(body.medical_history).toBeUndefined();
    expect(body.family_medical_history).toBeUndefined();
    expect(body.medications).toBeUndefined();
  });
});
