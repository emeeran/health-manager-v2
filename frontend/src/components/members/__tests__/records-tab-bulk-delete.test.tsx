import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { RecordsTab } from "../records-tab";
import type { HealthRecord } from "../../../lib/types/record";

vi.mock("../../../lib/api/records", () => ({
  deleteRecords: vi.fn(),
}));

import { deleteRecords } from "../../../lib/api/records";

// RecordsTab mutates the SWR key `/members/{id}/records` after deleting;
// the real cache isn't populated in this test, so a no-op mutate is enough.
vi.mock("swr", async (importOriginal) => {
  const actual = await importOriginal<typeof import("swr")>();
  return { ...actual, useSWRConfig: () => ({ mutate: vi.fn() }) };
});

function record(id: string, date: string): HealthRecord {
  return {
    id,
    member_id: "mem1",
    record_type: "doctor_visit",
    record_date: date,
    record_time: null,
    clinical_data: null,
    diagnosis: null,
    investigations: null,
    prescription_text: null,
    summary: null,
    doctor_name: null,
    provider_id: null,
    provider_name: null,
    tags: [],
    is_deleted: false,
    created_at: `${date}T00:00:00Z`,
    attachments: [],
  };
}

beforeEach(() => {
  vi.mocked(deleteRecords).mockReset();
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("RecordsTab bulk delete", () => {
  it("selects records and deletes them in one call", async () => {
    vi.mocked(deleteRecords).mockResolvedValue({
      deleted: 2,
      not_found: [],
    });
    render(
      <MemoryRouter>
        <RecordsTab
          records={[
            record("r1", "2026-09-01"),
            record("r2", "2026-08-15"),
            record("r3", "2026-08-01"),
          ]}
          isLoading={false}
          memberId="mem1"
          memberName="Asha"
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /select/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /2026-09-01/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /2026-08-01/ }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /delete selected/i }),
    );
    await waitFor(() => {
      expect(deleteRecords).toHaveBeenCalledWith("mem1", ["r1", "r3"]);
    });
    // Selection mode exits after a clean delete.
    expect(screen.queryByRole("toolbar", { name: /bulk actions/i })).toBeNull();
  });

  it("tapping a card in select mode toggles it instead of navigating", () => {
    render(
      <MemoryRouter>
        <RecordsTab
          records={[record("r1", "2026-09-01")]}
          isLoading={false}
          memberId="mem1"
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /select/i }));
    // Card is a Link; in select mode clicking it must not navigate.
    const card = screen.getByRole("link", { name: /visit/i });
    fireEvent.click(card);
    expect(screen.getByText("1 selected")).toBeInTheDocument();
  });

  it("keeps selection mode open and reports when some ids were already gone", async () => {
    vi.mocked(deleteRecords).mockResolvedValue({
      deleted: 1,
      not_found: ["r2"],
    });
    render(
      <MemoryRouter>
        <RecordsTab
          records={[record("r1", "2026-09-01"), record("r2", "2026-08-01")]}
          isLoading={false}
          memberId="mem1"
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /select/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /2026-09-01/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /2026-08-01/ }));
    fireEvent.click(screen.getByRole("button", { name: /delete selected/i }));
    expect(
      await screen.findByText(/1 deleted — 1 were already gone/i),
    ).toBeInTheDocument();
  });
});
