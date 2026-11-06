import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProviderEditDialog } from "../provider-edit-dialog";
import type { Provider } from "../../../lib/types/provider";

vi.mock("../../../lib/api/providers", () => ({
  updateProvider: vi.fn(),
}));

import { updateProvider } from "../../../lib/api/providers";

const PROVIDER: Provider = {
  id: "p-1",
  name: "Dr Priya Rao",
  specialty: "Cardiology",
  hospital: "City Hospital",
  phone: "555-0100",
  notes: null,
  created_at: "2026-01-01T00:00:00Z",
};

function renderDialog(
  overrides: Partial<Parameters<typeof ProviderEditDialog>[0]> = {},
) {
  return render(
    <ProviderEditDialog
      provider={PROVIDER}
      onClose={vi.fn()}
      onSaved={vi.fn()}
      {...overrides}
    />,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProviderEditDialog", () => {
  it("renders prefilled from the current provider", () => {
    renderDialog();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe(
      "Dr Priya Rao",
    );
    expect((screen.getByLabelText("Specialty") as HTMLInputElement).value).toBe(
      "Cardiology",
    );
    expect(
      (screen.getByLabelText("Hospital / clinic") as HTMLInputElement).value,
    ).toBe("City Hospital");
    expect((screen.getByLabelText("Phone") as HTMLInputElement).value).toBe(
      "555-0100",
    );
  });

  it("PATCHes the edited fields and fires onSaved", async () => {
    const onSaved = vi.fn();
    vi.mocked(updateProvider).mockResolvedValue({
      ...PROVIDER,
      name: "Dr Priya Rao-Menon",
    });
    renderDialog({ onSaved });

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Dr Priya Rao-Menon" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(updateProvider).toHaveBeenCalledWith(
      "p-1",
      expect.objectContaining({ name: "Dr Priya Rao-Menon" }),
    );
  });

  it("shows an error banner and stays open when the save fails", async () => {
    vi.mocked(updateProvider).mockRejectedValue(new Error("Network down"));
    const onSaved = vi.fn();
    renderDialog({ onSaved });

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Network down");
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByTestId("provider-edit-dialog")).toBeDefined();
  });

  it("empty optional fields are sent as null, not dropped", async () => {
    vi.mocked(updateProvider).mockResolvedValue(PROVIDER);
    renderDialog();

    fireEvent.change(screen.getByLabelText("Phone"), {
      target: { value: "" },
    });

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(updateProvider).toHaveBeenCalled());
    const body = vi.mocked(updateProvider).mock.calls[0][1];
    expect(body.phone).toBeNull();
    expect(body.notes).toBeNull();
  });

  it("cancel closes without saving", () => {
    const onClose = vi.fn();
    renderDialog({ onClose });

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
    expect(updateProvider).not.toHaveBeenCalled();
  });
});
