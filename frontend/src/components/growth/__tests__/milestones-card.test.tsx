import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MilestonesCard from "../milestones-card";
import { getMilestones } from "../../../lib/api/growth";
import type { MilestonesResponse } from "../../../lib/types/growth";

vi.mock("../../../lib/api/growth", () => ({
  getMilestones: vi.fn(),
  setMilestone: vi.fn(),
}));

function response(ageMonths: number | null): MilestonesResponse {
  return {
    age_months: ageMonths,
    rows: [
      {
        key: "walks",
        label: "Walks a few steps",
        age_months: 12,
        achieved: false,
        achieved_on: null,
        expected: "upcoming",
      },
    ],
  };
}

describe("MilestonesCard — children only", () => {
  it("renders the checklist for a young child", async () => {
    vi.mocked(getMilestones).mockResolvedValue(response(20));
    const { container } = render(<MilestonesCard memberId="young" />);
    expect(
      await screen.findByRole("checkbox", { name: "Walks a few steps" }),
    ).toBeInTheDocument();
    expect(container.firstChild).not.toBeNull();
  });

  it("hides for adults", async () => {
    vi.mocked(getMilestones).mockResolvedValue(response(300));
    const { container } = render(<MilestonesCard memberId="adult" />);
    await waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("hides when the member has no birth date", async () => {
    vi.mocked(getMilestones).mockResolvedValue(response(null));
    const { container } = render(<MilestonesCard memberId="nodob" />);
    await waitFor(() => expect(container.firstChild).toBeNull());
  });
});
