import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MedicationManager } from "../medication-manager";
import type { Medication } from "../../../lib/types/medication";

vi.mock("../../../lib/api/medications", () => ({
  createMedication: vi.fn(),
  deleteMedication: vi.fn(),
  updateMedication: vi.fn(),
}));
vi.mock("../../../lib/api/providers", () => ({
  listProviders: vi.fn().mockResolvedValue([]),
}));

import {
  createMedication,
  updateMedication,
} from "../../../lib/api/medications";

const MED: Medication = {
  id: "m1",
  member_id: "mem1",
  medicine: "Metformin",
  dose_form: "Tab",
  dosage: "500 mg",
  timing: "after food",
  duration_days: null,
  start_date: "2026-05-01",
  schedule_type: "daily",
  schedule_json: { slots: ["morning"], slot_times: { morning: "08:30" } },
  provider_name: "Dr Mehta",
  notes: null,
  status: "active",
  created_at: "2026-05-01T00:00:00Z",
};

function renderManager() {
  return render(
    <MedicationManager
      memberId="mem1"
      medications={[MED]}
      isLoading={false}
      onChange={() => {}}
    />,
  );
}

beforeEach(() => {
  vi.mocked(createMedication).mockReset();
  vi.mocked(updateMedication).mockReset();
});

describe("MedicationManager — schedule table", () => {
  it("renders the schedule table with dose-time columns per the mockup", () => {
    renderManager();
    expect(screen.getByText("Metformin")).toBeInTheDocument();
    expect(screen.getByText("500 mg")).toBeInTheDocument();
    // One column per slot in use, cell showing the medicine's own clock time.
    expect(
      screen.getByRole("columnheader", { name: "Morning" }),
    ).toBeInTheDocument();
    expect(screen.getByText("08:30")).toBeInTheDocument();
    expect(screen.getByText("after food")).toBeInTheDocument();
    expect(screen.getByText("Until next review")).toBeInTheDocument();
    expect(screen.getByText("Dr Mehta")).toBeInTheDocument();
  });

  it("opens the edit dialog prefilled and PATCHes the widened fields", async () => {
    vi.mocked(updateMedication).mockResolvedValue(MED);
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: /edit metformin/i }));
    const nameInput = screen.getByLabelText("Name") as HTMLInputElement;
    expect(nameInput.value).toBe("Metformin");
    expect(screen.getByLabelText("Food")).toBeInTheDocument();

    fireEvent.change(nameInput, { target: { value: "Syndopa 110" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(updateMedication).toHaveBeenCalledWith("mem1", "m1", {
        medicine: "Syndopa 110",
        dose_form: "Tab",
        dosage: "500 mg",
        timing: "after food",
        duration_days: null,
        provider_name: "Dr Mehta",
        status: "active",
        slots: ["morning"],
        slot_times: { morning: "08:30" },
      });
    });
    await waitFor(() => {
      // Dialog closed again after a successful save.
      expect(
        screen.queryByRole("button", { name: /save changes/i }),
      ).not.toBeInTheDocument();
    });
  });
});

describe("MedicationManager", () => {
  it("keeps the entry form collapsed until Add medicine is pressed", () => {
    renderManager();
    expect(screen.getByText("Metformin")).toBeInTheDocument();
    expect(screen.queryByLabelText("Add medicine")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /add medicine/i }),
    ).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(screen.getByRole("button", { name: /add medicine/i }));
    expect(screen.getByLabelText(/add medicine/i)).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
  });

  it("hides rarely-used fields behind More options", () => {
    renderManager();
    fireEvent.click(screen.getByRole("button", { name: /add medicine/i }));
    expect(screen.queryByText("Prescribed by")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /more options/i }));
    expect(screen.getByText("Prescribed by")).toBeInTheDocument();
    expect(screen.getByText("Duration (days)")).toBeInTheDocument();
    expect(screen.getByText("Start date")).toBeInTheDocument();
  });

  it("creates the medicine and collapses the form again", async () => {
    vi.mocked(createMedication).mockResolvedValue(MED);
    renderManager();
    fireEvent.click(screen.getByRole("button", { name: /add medicine/i }));

    fireEvent.change(screen.getByPlaceholderText("e.g. Metformin"), {
      target: { value: "Amlodipine" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^add medicine$/i }));

    await waitFor(() => {
      expect(createMedication).toHaveBeenCalledWith(
        "mem1",
        expect.objectContaining({ medicine: "Amlodipine" }),
      );
    });
    await waitFor(() => {
      // Form collapsed again after a successful save.
      expect(screen.queryByLabelText("Add medicine")).not.toBeInTheDocument();
    });
  });
});
