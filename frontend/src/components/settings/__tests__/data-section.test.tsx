import { render, screen } from "@testing-library/react";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../../lib/i18n";
import { DataSection } from "../data-section";

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

function makeFetchMock(handler: (url: string) => MockResponseInit) {
  return vi.fn(async (input: RequestInfo | URL) =>
    mockJsonResponse(handler(String(input))),
  );
}

function renderSection() {
  return render(
    <SWRConfig value={{ provider: () => new Map() }}>
      <I18nProvider>
        <DataSection />
      </I18nProvider>
    </SWRConfig>,
  );
}

const HEALTHY = {
  ok: true,
  engine: "sqlite",
  integrity_check: ["ok"],
  orphans: [],
  orphan_count: 0,
  attachment_check: {
    checked: 12,
    missing: 0,
    missing_paths: [],
    sample_limit: 25,
  },
  duration_ms: 7,
  notes: [],
};

const PROBLEMS = {
  ok: true,
  engine: "sqlite",
  integrity_check: ["ok"],
  orphans: [
    {
      table: "vitals",
      column: "member_id",
      target: "family_members",
      count: 3,
    },
  ],
  orphan_count: 3,
  attachment_check: {
    checked: 12,
    missing: 2,
    missing_paths: ["a", "b"],
    sample_limit: 25,
  },
  duration_ms: 9,
  notes: ["2 sampled attachment file(s) are missing from storage."],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DataSection", () => {
  it("renders a healthy integrity report", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/database/integrity")
          ? { status: 200, body: HEALTHY }
          : url.endsWith("/backup/list")
            ? { status: 200, body: [] }
            : { status: 200, body: {} },
      ),
    );

    renderSection();

    expect(screen.getByRole("region", { name: "Data" })).toBeInTheDocument();
    await screen.findByText("Database is healthy");
    expect(
      screen.getByText("No orphaned references found."),
    ).toBeInTheDocument();
    expect(screen.getByText("sqlite")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: /backup & restore/i }),
    ).toBeInTheDocument();
  });

  it("flags integrity problems with orphan counts", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/database/integrity")
          ? { status: 200, body: PROBLEMS }
          : url.endsWith("/backup/list")
            ? { status: 200, body: [] }
            : { status: 200, body: {} },
      ),
    );

    renderSection();

    await screen.findByText("Integrity problems detected");
    expect(screen.getAllByText("3").length).toBeGreaterThan(0); // orphan total + row
    expect(screen.getByText("vitals")).toBeInTheDocument();
    expect(screen.getByText(/member_id → family_members/)).toBeInTheDocument();
    expect(screen.getByText(/missing from storage/)).toBeInTheDocument();
  });

  it("shows an alert when the integrity request fails", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) =>
        url.endsWith("/database/integrity")
          ? { status: 500, body: { detail: "boom" } }
          : url.endsWith("/backup/list")
            ? { status: 200, body: [] }
            : { status: 200, body: {} },
      ),
    );

    renderSection();

    await screen.findByText("Could not load the integrity report.");
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
