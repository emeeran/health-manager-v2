import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemberEditDialog } from "../member-edit-dialog";
import type { Member } from "../../../lib/types/member";

vi.mock("../../../lib/api/members", () => ({
  updateMember: vi.fn(),
}));

import { updateMember } from "../../../lib/api/members";

const MEMBER: Member = {
  id: "m-1",
  name: "Asha",
  relationship: "child",
  birth_date: "2015-03-14",
  sex: "female",
  phone: null,
  address: null,
  blood_group: "O+",
  medical_history: "Asthma at age 4",
  family_medical_history: "Diabetes (mother)",
  current_medications: null,
  emergency_contact_name: "Meeran",
  emergency_contact_phone: "555-0100",
  notes: null,
  created_at: "2026-01-01T00:00:00Z",
};

function renderDialog(
  overrides: Partial<Parameters<typeof MemberEditDialog>[0]> = {},
) {
  return render(
    <MemberEditDialog
      member={MEMBER}
      onClose={vi.fn()}
      onSaved={vi.fn()}
      {...overrides}
    />,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("MemberEditDialog", () => {
  it("renders prefilled from the current member", () => {
    renderDialog();
    expect((screen.getByLabelText("Full name") as HTMLInputElement).value).toBe(
      "Asha",
    );
    expect(
      (screen.getByLabelText("Blood group") as HTMLInputElement).value,
    ).toBe("O+");
    expect(
      (screen.getByLabelText("Medical history") as HTMLTextAreaElement).value,
    ).toBe("Asthma at age 4");
    expect(
      (screen.getByLabelText("Family medical history") as HTMLTextAreaElement)
        .value,
    ).toBe("Diabetes (mother)");
    expect(
      (screen.getByLabelText("Emergency contact") as HTMLInputElement).value,
    ).toBe("Meeran");
  });

  it("PATCHes the edited fields and fires onSaved", async () => {
    const onSaved = vi.fn();
    vi.mocked(updateMember).mockResolvedValue({
      ...MEMBER,
      name: "Asha R",
    });
    renderDialog({ onSaved });

    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Asha R" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(updateMember).toHaveBeenCalledWith(
      "m-1",
      expect.objectContaining({
        name: "Asha R",
        sex: "female",
        blood_group: "O+",
        medical_history: "Asthma at age 4",
        family_medical_history: "Diabetes (mother)",
      }),
    );
  });

  it("shows an error banner and stays open when the save fails", async () => {
    vi.mocked(updateMember).mockRejectedValue(new Error("Network down"));
    const onSaved = vi.fn();
    renderDialog({ onSaved });

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Network down");
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByTestId("member-edit-dialog")).toBeDefined();
  });

  it("empty optional fields are sent as null, not dropped", async () => {
    vi.mocked(updateMember).mockResolvedValue(MEMBER);
    renderDialog();

    // Clear the prefilled values first.
    fireEvent.change(screen.getByLabelText("Phone"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("Medical history"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("Family medical history"), {
      target: { value: "" },
    });

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(updateMember).toHaveBeenCalled());
    const body = vi.mocked(updateMember).mock.calls[0][1];
    expect(body.phone).toBeNull();
    expect(body.notes).toBeNull();
    expect(body.medical_history).toBeNull();
    expect(body.family_medical_history).toBeNull();
  });

  it("sends the web fact-check consent toggle", async () => {
    vi.mocked(updateMember).mockResolvedValue({
      ...MEMBER,
      web_factcheck_consent: true,
    });
    renderDialog();

    const toggle = screen.getByLabelText(/allow external fact-checking/i);
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(updateMember).toHaveBeenCalled());
    expect(
      vi.mocked(updateMember).mock.calls[0][1].web_factcheck_consent,
    ).toBe(true);
  });
});
