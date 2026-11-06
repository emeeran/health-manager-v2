import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TrackPrescriptionMeds } from "../track-prescription-meds";
import type { HealthRecord } from "../../../lib/types/record";

vi.mock("../../../lib/api/medications", () => ({
  createMedication: vi.fn(),
  listMedications: vi.fn(),
}));

import {
  createMedication,
  listMedications,
} from "../../../lib/api/medications";

function recordWithMeds(meds: unknown): HealthRecord {
  return {
    id: "r1",
    member_id: "mem1",
    record_type: "prescription",
    record_date: "2026-09-01",
    record_time: null,
    clinical_data: { medications: meds },
    diagnosis: null,
    investigations: null,
    prescription_text: null,
    summary: null,
    doctor_name: null,
    provider_id: null,
    provider_name: null,
    tags: [],
    is_deleted: false,
    created_at: "2026-09-01T00:00:00Z",
    attachments: [],
  };
}

beforeEach(() => {
  vi.mocked(createMedication).mockReset();
  vi.mocked(listMedications).mockReset();
  vi.mocked(createMedication).mockResolvedValue({ id: "new" } as never);
});

describe("TrackPrescriptionMeds", () => {
  it("offers to track extracted medicines that aren't tracked yet", async () => {
    vi.mocked(listMedications).mockResolvedValue([
      { id: "m1", medicine: "Metformin", status: "active" },
    ] as never);
    render(
      <TrackPrescriptionMeds
        memberId="mem1"
        record={recordWithMeds([
          { name: "Metformin", dosage: "500 mg" },
          { name: "Amlodipine", dosage: "5 mg", timing: "morning" },
        ])}
      />,
    );

    expect(
      await screen.findByText(/1 medicine in this prescription isn't tracked/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Amlodipine — 5 mg, morning/)).toBeInTheDocument();
    expect(screen.queryByText(/Metformin —/)).not.toBeInTheDocument();
  });

  it("creates the missing medicines as daily and confirms", async () => {
    vi.mocked(listMedications).mockResolvedValue([]);
    render(
      <TrackPrescriptionMeds
        memberId="mem1"
        record={recordWithMeds([{ name: "Amlodipine", dosage: "5 mg" }])}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: /add to today's medicines/i,
      }),
    );

    await waitFor(() => {
      expect(createMedication).toHaveBeenCalledWith("mem1", {
        medicine: "Amlodipine",
        record_id: "r1",
        dosage: "5 mg",
        schedule_type: "daily",
      });
    });
    expect(
      await screen.findByText(/they now appear in today's medicines/i),
    ).toBeInTheDocument();
  });

  it("renders nothing when the record has no extracted medications", () => {
    render(
      <TrackPrescriptionMeds
        memberId="mem1"
        record={recordWithMeds(undefined)}
      />,
    );
    expect(
      screen.queryByTestId("track-prescription-meds"),
    ).not.toBeInTheDocument();
  });
});
