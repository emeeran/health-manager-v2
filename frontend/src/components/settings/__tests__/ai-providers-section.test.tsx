import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../lib/api-client";
import { AiProvidersSection } from "../ai-providers-section";

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

function stubEndpoints() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/household/ai-config"))
      return mockJsonResponse({
        status: 200,
        body: {
          primary_provider: "auto",
          providers: [{ name: "deepseek", enabled: true }],
        },
      });
    if (url.endsWith("/system/ai-providers"))
      return mockJsonResponse({
        status: 200,
        body: {
          providers: [
            { name: "deepseek", model: "deepseek-chat", local: false },
            { name: "ollama", model: "qwen3:4b", local: true },
          ],
        },
      });
    if (url.endsWith("/system/provider-keys"))
      return mockJsonResponse({
        status: 200,
        body: {
          keys: [
            {
              name: "DEEPSEEK_API_KEY",
              set: true,
              source: "db",
              value: "sk-2…",
            },
            {
              name: "DEEPSEEK_BASE_URL",
              set: false,
              source: "none",
              value: "",
            },
            {
              name: "OLLAMA_BASE_URL",
              set: true,
              source: "env",
              value: "http://localhost:11434",
            },
            {
              name: "OPENAI_API_KEY",
              set: false,
              source: "none",
              value: "",
            },
            {
              name: "OPENAI_BASE_URL",
              set: false,
              source: "none",
              value: "",
            },
          ],
        },
      });
    if (init?.method === "PUT" && url.includes("/provider-keys"))
      return mockJsonResponse({ status: 200, body: {} });
    return mockJsonResponse({ status: 200, body: {} });
  });
}

function renderSection() {
  return render(
    <SWRConfig
      value={{
        fetcher: (key) => apiRequest(String(key)),
        provider: () => new Map(),
      }}
    >
      <AiProvidersSection />
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AiProvidersSection (compact board)", () => {
  it("renders one row per configured provider and hides the rest", async () => {
    vi.stubGlobal("fetch", stubEndpoints());
    renderSection();

    // deepseek (key saved + override) and ollama (base URL from env) show;
    // openai has nothing configured and stays behind the expander.
    const deepseek = await screen.findByTestId("provider-row-deepseek");
    expect(deepseek.textContent).toContain("deepseek-chat");
    expect(screen.getByTestId("provider-row-ollama")).toBeInTheDocument();
    expect(screen.queryByTestId("provider-row-openai")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /show 7 more providers/i }),
    ).toBeInTheDocument();
  });

  it("expands a row to reveal the key field and override controls", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", stubEndpoints());
    renderSection();

    const row = await screen.findByTestId("provider-row-deepseek");
    await user.click(within(row).getByRole("button", { expanded: false }));
    expect(
      await screen.findByLabelText("API key for deepseek"),
    ).toBeInTheDocument();
    expect(screen.getByText(/remove override/i)).toBeInTheDocument();
  });

  it("saves a new key via the expanded panel", async () => {
    const user = userEvent.setup();
    const fetchMock = stubEndpoints();
    vi.stubGlobal("fetch", fetchMock);
    renderSection();

    const row = await screen.findByTestId("provider-row-deepseek");
    await user.click(within(row).getByRole("button", { expanded: false }));
    await user.type(
      await screen.findByLabelText("API key for deepseek"),
      "sk-new",
    );
    await user.click(screen.getByRole("button", { name: /save key/i }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).endsWith("/system/provider-keys/DEEPSEEK_API_KEY") &&
            init?.method === "PUT",
        ),
      ).toBe(true);
    });
  });

  it("refresh shows only live models and purges a stale override", async () => {
    const user = userEvent.setup();
    const savedConfigs: unknown[] = [];
    // The persisted deepseek override points at a model the key's
    // catalogue no longer serves.
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/household/ai-config") && init?.method === "PUT") {
        savedConfigs.push(JSON.parse(String(init.body)));
        return mockJsonResponse({ status: 200, body: {} });
      }
      if (url.endsWith("/household/ai-config"))
        return mockJsonResponse({
          status: 200,
          body: {
            primary_provider: "auto",
            providers: [
              { name: "deepseek", enabled: true, model: "llama-old" },
            ],
          },
        });
      if (url.endsWith("/system/ai-providers"))
        return mockJsonResponse({
          status: 200,
          body: {
            providers: [{ name: "deepseek", model: "llama-old", local: false }],
          },
        });
      if (url.endsWith("/system/ai-providers/deepseek/models"))
        return mockJsonResponse({
          status: 200,
          body: { models: ["deepseek-chat", "deepseek-reasoner"] },
        });
      if (url.endsWith("/system/provider-keys"))
        return mockJsonResponse({
          status: 200,
          body: {
            keys: [
              {
                name: "DEEPSEEK_API_KEY",
                set: true,
                source: "db",
                value: "sk-2…",
              },
            ],
          },
        });
      return mockJsonResponse({ status: 200, body: {} });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderSection();

    const row = await screen.findByTestId("provider-row-deepseek");
    await user.click(
      within(row).getByRole("button", { name: /refresh models for deepseek/i }),
    );

    const input = await screen.findByLabelText("Model override for deepseek");
    expect(input.getAttribute("list")).toBe("models-deepseek");
    const options = Array.from(
      input.ownerDocument.querySelectorAll("#models-deepseek option"),
    ).map((o) => o.getAttribute("value"));
    expect(options).toEqual(["deepseek-chat", "deepseek-reasoner"]);
    await waitFor(() => {
      const put = savedConfigs.at(-1) as {
        providers: { name: string; model: string | null }[];
      };
      expect(put.providers[0].model).toBeNull();
    });
  });
});
