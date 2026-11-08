import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../lib/api/insights", () => ({
  getLatestInsight: vi.fn().mockResolvedValue(null),
  streamInsight: vi.fn().mockResolvedValue({
    id: "ins1",
    kind: "pre_consultation",
    content: "note body",
    sources: null,
    verification_id: null,
    provider_used: "fake",
    created_at: "2026-11-08T00:00:00Z",
  }),
}));

import { streamInsight } from "../../../lib/api/insights";
import { InsightTool } from "../insight-tool";

// Unique per test: the module-level SWR cache would otherwise hand a
// previously-generated insight to the next render ("Regenerate" ≠ "Generate").
let seq = 0;
const base = () => ({
  memberId: `mem-${++seq}`,
  kind: "pre_consultation" as const,
  description: "test",
  confirmBeforeRun: true,
});

describe("InsightTool confirmBeforeRun", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function startConfirm() {
    render(<InsightTool {...base()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Generate" }));
    const dialog = await screen.findByRole("alertdialog");
    // The complaints textarea opens focused — symptom entry is the primary intent.
    expect(screen.getByRole("textbox")).toHaveFocus();
    return dialog;
  }

  it("runs on C keypress when focus is outside a field", async () => {
    await startConfirm();
    await userEvent.click(screen.getByText("Generate from this member's current records?"));
    await userEvent.keyboard("c");
    expect(streamInsight).toHaveBeenCalledTimes(1);
  });

  it("runs on Enter keypress when focus is outside a field", async () => {
    await startConfirm();
    await userEvent.click(screen.getByText("Generate from this member's current records?"));
    await userEvent.keyboard("{Enter}");
    expect(streamInsight).toHaveBeenCalledTimes(1);
  });

  it("types into the complaints field, then Continue passes the note", async () => {
    await startConfirm();
    await userEvent.keyboard("Headache for 3 days, poor sleep");
    expect(streamInsight).not.toHaveBeenCalled(); // "c" typed as text, not a command
    await userEvent.click(screen.getByRole("button", { name: "Continue (C)" }));
    expect(streamInsight).toHaveBeenCalledTimes(1);
    expect(streamInsight).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.anything(),
      expect.objectContaining({ note: "Headache for 3 days, poor sleep" }),
    );
  });

  it("Ctrl+Enter from the complaints field continues with the note", async () => {
    await startConfirm();
    await userEvent.keyboard("Dizzy in the mornings");
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    expect(streamInsight).toHaveBeenCalledTimes(1);
    expect(streamInsight).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.anything(),
      expect.objectContaining({ note: "Dizzy in the mornings" }),
    );
  });

  it("sends no note param when the field is left empty", async () => {
    await startConfirm();
    await userEvent.click(screen.getByRole("button", { name: "Continue (C)" }));
    expect(streamInsight).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.anything(),
      expect.objectContaining({ note: "" }),
    );
  });

  it("Escape cancels, also from inside the complaints field", async () => {
    await startConfirm();
    await userEvent.keyboard("{Escape}");
    expect(streamInsight).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Generate" })).toBeDefined();
  });

  it("cancels via the Cancel button click", async () => {
    await startConfirm();
    await userEvent.click(screen.getByRole("button", { name: "Cancel (Esc)" }));
    expect(streamInsight).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("ignores bare keystrokes typed into a form field", async () => {
    await startConfirm();
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "n" });
    expect(streamInsight).not.toHaveBeenCalled();
    // Dialog still open — "n" was text, not cancel.
    expect(screen.getByRole("alertdialog")).toBeDefined();
  });
});
