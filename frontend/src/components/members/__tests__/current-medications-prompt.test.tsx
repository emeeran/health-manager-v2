import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CurrentMedicationsPrompt } from "../current-medications-prompt";

vi.mock("../../../lib/api/members", () => ({
  getMember: vi.fn().mockResolvedValue({
    id: "mem1",
    name: "Asha",
    current_medications: "Metformin — 500 mg",
  }),
  mergeCurrentMedications: vi.fn(),
  updateMember: vi.fn(),
}));

import {
  mergeCurrentMedications,
  updateMember,
} from "../../../lib/api/members";

beforeEach(() => {
  vi.mocked(mergeCurrentMedications).mockReset();
  vi.mocked(updateMember).mockReset();
  vi.mocked(updateMember).mockResolvedValue({ id: "mem1" } as never);
});

describe("CurrentMedicationsPrompt", () => {
  it("merges on demand, lets the user edit, and saves via PATCH", async () => {
    vi.mocked(mergeCurrentMedications).mockResolvedValue({
      suggestion: "Metformin — 500 mg\nAmlodipine — 5 mg",
    });
    render(<CurrentMedicationsPrompt memberId="mem1" />);

    // Member loads async via SWR — the "update" variant lands once it has.
    expect(
      await screen.findByText(/update this member's current-medications list/i),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /merge with tracked medications/i }),
    );
    expect(mergeCurrentMedications).toHaveBeenCalledWith("mem1");

    const textarea = await screen.findByRole("textbox");
    expect(textarea).toHaveValue("Metformin — 500 mg\nAmlodipine — 5 mg");

    fireEvent.change(textarea, {
      target: { value: "Metformin — 500 mg\nAmlodipine — 5 mg, morning" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save list/i }));

    await waitFor(() => {
      expect(updateMember).toHaveBeenCalledWith("mem1", {
        current_medications: "Metformin — 500 mg\nAmlodipine — 5 mg, morning",
      });
    });
    expect(
      await screen.findByText(/current medications updated/i),
    ).toBeInTheDocument();
  });

  it("dismisses without touching the member record", async () => {
    render(<CurrentMedicationsPrompt memberId="mem1" />);
    fireEvent.click(
      screen.getByRole("button", {
        name: /dismiss current medications prompt/i,
      }),
    );
    expect(screen.queryByTestId("current-medications-prompt")).toBeNull();
    expect(updateMember).not.toHaveBeenCalled();
  });

  it("surfaces merge errors instead of dying", async () => {
    vi.mocked(mergeCurrentMedications).mockRejectedValue(
      new Error("No AI provider available"),
    );
    render(<CurrentMedicationsPrompt memberId="mem1" />);
    fireEvent.click(
      screen.getByRole("button", { name: /merge with tracked medications/i }),
    );
    expect(
      await screen.findByText(/no ai provider available/i),
    ).toBeInTheDocument();
  });
});
