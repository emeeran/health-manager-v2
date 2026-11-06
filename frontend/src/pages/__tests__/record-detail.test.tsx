import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../lib/api-client";
import { streamExtract } from "../../lib/api/ai";
import RecordDetail from "../record-detail";
import type { HealthRecord } from "../../lib/types/record";

vi.mock("../../lib/api/ai", () => ({
  streamExtract: vi.fn(),
}));

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

function recordFixture(overrides: Partial<HealthRecord> = {}): HealthRecord {
  return {
    id: "r1",
    member_id: "m1",
    record_type: "doctor_visit",
    record_date: "2026-11-01",
    record_time: null,
    clinical_data: null,
    diagnosis: null,
    investigations: null,
    prescription_text: null,
    summary: "Follow-up visit.",
    doctor_name: "Dr Mehta",
    provider_id: null,
    provider_name: null,
    tags: [],
    confidentiality_level: "household",
    attachments: [],
    is_deleted: false,
    created_at: "2026-11-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage(record: HealthRecord) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/records/r1"))
        return mockJsonResponse({ status: 200, body: record });
      return mockJsonResponse({ status: 200, body: [] });
    }),
  );
  return render(
    <SWRConfig
      value={{
        fetcher: (key) => apiRequest(String(key)),
        provider: () => new Map(),
      }}
    >
      <MemoryRouter initialEntries={["/members/m1/records/r1"]}>
        <Routes>
          <Route
            path="/members/:memberId/records/:recordId"
            element={<RecordDetail />}
          />
        </Routes>
      </MemoryRouter>
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("Record detail — structured data", () => {
  it("renders persisted clinical data alongside the record", async () => {
    renderPage(
      recordFixture({
        clinical_data: {
          medications: [{ name: "SYNDOPA 110mg", dosage: "1-1-1" }],
          labs: [{ name: "HbA1c", result: "7.8", units: "%", flag: "high" }],
        },
      }),
    );

    expect(await screen.findByText("Structured data")).toBeInTheDocument();
    // Both the structured view and the med-tracking banner name the drug.
    expect(screen.getAllByText(/SYNDOPA 110mg/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/HbA1c/).length).toBeGreaterThan(0);
  });

  it("prompts to track extracted meds even on a doctor visit", async () => {
    renderPage(
      recordFixture({
        clinical_data: {
          medications: [{ name: "Amlodipine", dosage: "5 mg" }],
        },
      }),
    );

    expect(
      await screen.findByTestId("track-prescription-meds"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/medicine in this prescription isn't tracked yet/i),
    ).toBeInTheDocument();
  });

  it("shows no structured-data section without clinical data", async () => {
    renderPage(recordFixture());

    expect(await screen.findByText("Follow-up visit.")).toBeInTheDocument();
    expect(screen.queryByText("Structured data")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("track-prescription-meds"),
    ).not.toBeInTheDocument();
  });

  it("auto-extracts attachments after the wizard hand-off (?extract=1)", async () => {
    const { attachmentDownloadUrl } = await import("../../lib/api/attachments");
    const downloadUrl = attachmentDownloadUrl("a1");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/records/r1"))
        return mockJsonResponse({
          status: 200,
          body: recordFixture({
            attachments: [
              {
                id: "a1",
                file_path: "x",
                content_hash: "h",
                file_size: 1,
                mime: "application/pdf",
                original_name: "rx-report.pdf",
                created_at: "2026-11-01T00:00:00Z",
              },
            ],
          }),
        });
      if (url === downloadUrl)
        return {
          ok: true,
          status: 200,
          blob: async () => new Blob(["pdf"], { type: "application/pdf" }),
        };
      if (url.endsWith("/apply-extraction"))
        return mockJsonResponse({
          status: 200,
          body: { record_id: "r1", labs_created: 2, vitals_created: 0 },
        });
      return mockJsonResponse({ status: 200, body: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.mocked(streamExtract).mockResolvedValue({
      clinical_data: { medications: [{ name: "Amlodipine" }], labs: [] },
      summary: null,
      provider_used: "test",
      verification_id: null,
    });

    render(
      <SWRConfig
        value={{
          fetcher: (key) => apiRequest(String(key)),
          provider: () => new Map(),
        }}
      >
        <MemoryRouter initialEntries={["/members/m1/records/r1?extract=1"]}>
          <Routes>
            <Route
              path="/members/:memberId/records/:recordId"
              element={<RecordDetail />}
            />
          </Routes>
        </MemoryRouter>
      </SWRConfig>,
    );

    // Extraction ran with provenance and applied itself to the record.
    await waitFor(() =>
      expect(streamExtract).toHaveBeenCalledWith(
        "m1",
        expect.anything(),
        expect.any(Function),
        expect.objectContaining({ recordId: "r1" }),
      ),
    );
    await waitFor(() => {
      const apply = fetchMock.mock.calls.find(([url]) =>
        String(url).endsWith("/apply-extraction"),
      );
      expect(apply).toBeDefined();
    });
    // Queue shows the document as processed with saved counts.
    const queueItem = await screen.findByTestId("extract-queue-item");
    expect(queueItem.textContent).toContain("rx-report.pdf");
    expect(queueItem.textContent).toContain("2 lab(s)");
  });
});
