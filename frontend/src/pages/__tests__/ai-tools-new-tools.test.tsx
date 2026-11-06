import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../lib/api-client";
import { A5NoteView } from "../../components/ai-tools/a5-note-view";
import PriceComparisonPage from "../ai-tools/price-comparison";
import VisitSummaryPage from "../ai-tools/visit-summary";

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
    <SWRConfig value={{ fetcher: (key) => apiRequest(String(key)), provider: () => new Map() }}>
      <MemoryRouter>{ui}</MemoryRouter>
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("price comparison page", () => {
  it("renders the table with match-null rows marked", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url, init) => {
        if (url.endsWith("/members")) {
          return { status: 200, body: [{ id: "m1", name: "Asha" }] };
        }
        if (url.includes("/medications")) {
          return {
            status: 200,
            body: [
              { id: "d1", medicine: "Metformin 500mg" },
              { id: "d2", medicine: "Mystery Pill" },
            ],
          };
        }
        if (url.endsWith("/drugs/price-compare") && init?.method === "POST") {
          return {
            status: 200,
            body: {
              items: [
                {
                  medicine: "Metformin 500mg",
                  match: "exact",
                  catalog_name: "Metformin 500mg Tablet",
                  manufacturer: "PMBJP",
                  ingredients: "Metformin",
                  package: "10's",
                  price: 3.2,
                  product_id: "1",
                },
                {
                  medicine: "Mystery Pill",
                  match: null,
                  catalog_name: null,
                  manufacturer: null,
                  ingredients: null,
                  package: null,
                  price: null,
                  product_id: null,
                },
              ],
              matched_count: 1,
              total_price: 3.2,
              narrative: "Metformin is 3.2; the catalog could not match Mystery Pill.",
              provider_used: "fake",
            },
          };
        }
        return { status: 200, body: [] };
      }),
    );

    renderWithProviders(<PriceComparisonPage />);

    const compare = await screen.findByRole("button", { name: /Compare prices/i });
    await waitFor(() => expect(compare).not.toBeDisabled());
    fireEvent.click(compare);

    expect(await screen.findByText("Metformin 500mg Tablet")).toBeInTheDocument();
    expect(screen.getByText("not matched")).toBeInTheDocument();
    expect(screen.getByText(/total ₹3.20/)).toBeInTheDocument();
    // The grounded narrative renders with its provider tag.
    expect(screen.getByText(/Metformin is 3.2/)).toBeInTheDocument();
    expect(screen.getByText(/Reference prices from the Jan Aushadhi catalog/)).toBeInTheDocument();
  });
});

describe("A5 note view", () => {
  it("renders fields and allows editing the discussion list", () => {
    render(
      <A5NoteView
        noteId="i1"
        note={{
          date: "2026-11-10",
          member_name: "Asha",
          chronic_conditions: ["T2D", "HTN"],
          chief_complaints: ["burning feet"],
          to_discuss: ["HbA1c control"],
          current_medications: ["Metformin 500 mg"],
        }}
      />,
    );

    expect(screen.getByText("Date:")).toBeInTheDocument();
    expect(screen.getByText("2026-11-10")).toBeInTheDocument();
    expect(screen.getByText(/Chronic:/)).toBeInTheDocument();
    expect(screen.getByText("T2D, HTN")).toBeInTheDocument();
    expect(screen.getByText(/C\/c:/)).toBeInTheDocument();
    expect(screen.getByText("burning feet")).toBeInTheDocument();

    const input = screen.getByLabelText("Discussion item 1") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Ask about dose switch" } });
    expect(input.value).toBe("Ask about dose switch");
    expect(screen.getByRole("button", { name: /Copy for WhatsApp/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Print \(A5\)/i })).toHaveAttribute(
      "href",
      "/ai-tools/pre-consultation/print",
    );
  });
});

describe("visit summary page", () => {
  it("picks the visit to summarize", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock((url) => {
        if (url.endsWith("/members")) {
          return { status: 200, body: [{ id: "m1", name: "Asha" }] };
        }
        if (url.includes("/records")) {
          return {
            status: 200,
            body: [
              {
                id: "r2",
                member_id: "m1",
                record_type: "doctor_visit",
                record_date: "2026-05-01",
                record_time: null,
                clinical_data: null,
                diagnosis: "Poor glycemic control",
                investigations: null,
                prescription_text: null,
                summary: null,
                doctor_name: "Dr. Rao",
                provider_id: null,
                provider_name: null,
                tags: [],
                is_deleted: false,
                created_at: "2026-05-01T00:00:00",
              },
            ],
          };
        }
        if (url.includes("/reports/latest")) {
          return { status: 200, body: null };
        }
        return { status: 200, body: [] };
      }),
    );

    renderWithProviders(<VisitSummaryPage />);

    expect(await screen.findByText(/Dr. Rao/)).toBeInTheDocument();
    expect(screen.getByText(/Poor glycemic control/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generate/i })).toBeInTheDocument();
  });
});
