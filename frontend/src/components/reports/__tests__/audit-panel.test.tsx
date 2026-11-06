import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import { AuditPanel } from "../audit-panel";
import { getVerification } from "../../../lib/api/ai";
import type { Verification } from "../../../lib/types/ai";

vi.mock("../../../lib/api/ai", () => ({
  getVerification: vi.fn(),
}));

const PASSED: Verification = {
  id: "v-1",
  status: "passed",
  notes: "One claim verified.",
  verifier_name: "fake",
  audit: {
    overall: "passed",
    summary: "One claim verified.",
    claims: [
      {
        claim: "HbA1c was 8.4 % on 2026-05-01.",
        category: "record_fact",
        verdict: "supported",
        severity: "info",
        evidence_ids: ["lab:1"],
        evidence: [
          {
            domain: "lab",
            ref: "lab:1",
            label: "HbA1c",
            value: "8.4 % [high]",
            date: "2026-05-01",
          },
        ],
        needs_web: false,
        web_query: null,
        web: null,
        note: null,
      },
    ],
    gaps: [],
    interactions: [],
    web_used: false,
    sources: [],
  },
};

const FLAGGED: Verification = {
  id: "v-2",
  status: "flagged",
  notes: "One contradiction.",
  verifier_name: "fake",
  audit: {
    overall: "flagged",
    summary: "One contradiction and one gap.",
    claims: [
      {
        claim: "HbA1c was 6.1 %.",
        category: "record_fact",
        verdict: "contradicted",
        severity: "critical",
        evidence_ids: ["lab:1"],
        evidence: [
          {
            domain: "lab",
            ref: "lab:1",
            label: "HbA1c",
            value: "8.4 % [high]",
            date: "2026-05-01",
          },
        ],
        needs_web: false,
        web_query: null,
        web: null,
        note: "The recorded value is 8.4 %.",
      },
      {
        claim: "An HbA1c of 8.4 % is above target.",
        category: "guideline",
        verdict: "external_verified",
        severity: "info",
        evidence_ids: [],
        evidence: [],
        needs_web: true,
        web_query: "HbA1c target",
        web: {
          query: "HbA1c target",
          results: [
            {
              title: "ADA guidance",
              url: "https://diabetes.example/guidance",
            },
          ],
        },
        note: "Guideline agrees.",
      },
    ],
    gaps: [
      { domain: "labs", status: "stale", detail: "Last labs were 400 days ago." },
    ],
    interactions: [
      {
        drugs: ["Metformin", "Warfarin"],
        severity: "moderate",
        description: "Monitor INR.",
      },
    ],
    web_used: true,
    sources: [
      { title: "ADA guidance", url: "https://diabetes.example/guidance" },
    ],
  },
};

function renderPanel() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <AuditPanel verificationId="v-1" />
    </SWRConfig>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("AuditPanel", () => {
  it("collapses a passed audit and expands it on demand", async () => {
    vi.mocked(getVerification).mockResolvedValue(PASSED);
    renderPanel();

    expect(await screen.findByText(/audit passed/i)).toBeDefined();
    expect(screen.queryByText("HbA1c was 8.4 % on 2026-05-01.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /view audit/i }));

    expect(screen.getByText("HbA1c was 8.4 % on 2026-05-01.")).toBeDefined();
    expect(screen.getByText("HbA1c").parentElement?.textContent).toContain(
      "8.4 % [high]",
    );
  });

  it("opens a flagged audit with contradictions, gaps and sources", async () => {
    vi.mocked(getVerification).mockResolvedValue(FLAGGED);
    renderPanel();

    expect(await screen.findByText(/audit needs review/i)).toBeDefined();
    expect(screen.getByText("HbA1c was 6.1 %.")).toBeDefined();
    expect(screen.getByText("Contradicted")).toBeDefined();
    expect(screen.getByText(/Last labs were 400 days ago/)).toBeDefined();
    expect(screen.getByText(/Metformin \+ Warfarin/)).toBeDefined();

    const links = screen.getAllByRole("link", { name: /ADA guidance/i });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0].getAttribute("rel")).toBe("noopener noreferrer");
    expect(links[0].getAttribute("href")).toBe(
      "https://diabetes.example/guidance",
    );
  });

  it("shows a pending state until the audit arrives", async () => {
    vi.mocked(getVerification).mockResolvedValue({
      id: "v-3",
      status: "pending",
      notes: null,
      audit: null,
    });
    renderPanel();

    expect(await screen.findByText(/auditing claims/i)).toBeDefined();
  });
});
