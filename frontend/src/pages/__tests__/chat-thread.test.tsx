import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { SWRConfig } from "swr";
import { ChatThread } from "../chat";

// Regression: the message-list fetcher was passed to SWR directly, so SWR
// fed it the full cache key ("/conversations/<id>/messages") as the
// conversation id — the request 404'd and assistant replies never rendered.
describe("ChatThread — message list fetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  beforeAll(() => {
    // The DOM environment doesn't implement scrolling.
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("requests the conversation's messages with a clean id", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/conversations/conv1/messages"))
        return {
          ok: true,
          status: 200,
          text: async () =>
            JSON.stringify([
              {
                id: "m1",
                role: "assistant",
                content: "DISPLAY-TEST-OK",
                verification_id: null,
                created_at: "2026-11-04T00:00:00Z",
              },
            ]),
        };
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify([]),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <SWRConfig value={{ provider: () => new Map() }}>
          <ChatThread
            conversationId="conv1"
            memberId={null}
            onChanged={() => {}}
          />
        </SWRConfig>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).endsWith("/api/v1/conversations/conv1/messages"),
        ),
      ).toBe(true);
    });
    // The reply from history renders in the thread.
    await screen.findByText("DISPLAY-TEST-OK");
    // And the URL was not double-encoded into a nested path.
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes("%2Fconversations%2F"),
      ),
    ).toBe(false);
  });

  it("renders assistant replies as GFM markdown, user messages as plain text", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/conversations/conv1/messages"))
        return {
          ok: true,
          status: 200,
          text: async () =>
            JSON.stringify([
              {
                id: "u1",
                role: "user",
                content: "1. not a list\n**literal asterisks**",
                verification_id: null,
                created_at: "2026-11-04T00:00:00Z",
              },
              {
                id: "a1",
                role: "assistant",
                content:
                  "## Medicines\n\nTake **metformin** with food:\n\n- 500 mg morning\n- 500 mg evening\n\n| Test | Value |\n| --- | --- |\n| HbA1c | 7.2 |",
                verification_id: null,
                created_at: "2026-11-04T00:00:01Z",
              },
            ]),
        };
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify([]),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <SWRConfig value={{ provider: () => new Map() }}>
          <ChatThread
            conversationId="conv1"
            memberId={null}
            onChanged={() => {}}
          />
        </SWRConfig>
      </MemoryRouter>,
    );

    // Assistant reply: heading, emphasis, list, and table all materialize.
    await screen.findByRole("heading", { name: "Medicines" });
    expect(screen.getByText("metformin").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "HbA1c" })).toBeInTheDocument();

    // User message: markdown characters stay literal (plain <p>, no <strong>).
    const userBubble = screen.getByText(
      (_, el) =>
        el?.tagName === "P" &&
        el.textContent === "1. not a list\n**literal asterisks**",
    );
    expect(userBubble.querySelector("strong")).toBeNull();
  });
});
