import { expect, test } from "@playwright/test";
import { createMember, freshSession } from "./helpers";

test.describe("Record wizard", () => {
  test("guided wizard: type → visit → clinical → review creates a record", async ({
    page,
  }) => {
    const username = `e2e-wiz-${Date.now()}`;
    const session = await freshSession(page, username);
    const memberId = await createMember(session, "Wizard Patient");
    await page.goto(`/members/${memberId}`);

    await page.getByRole("button", { name: "New record" }).click();
    const dialog = page.getByRole("dialog", { name: "New record" });
    await expect(
      dialog.getByRole("button", { name: "Guided wizard" }),
    ).toHaveAttribute("aria-pressed", "true");

    // Step 1 — type: advancing without a choice is blocked with a hint.
    await dialog.getByRole("button", { name: "Next" }).click();
    await expect(
      dialog.getByRole("alert").filter({ hasText: "record type" }),
    ).toBeVisible();
    await dialog.getByRole("button", { name: "Doctor visit" }).click();

    // Step 2 — visit details (date comes prefilled with today).
    await dialog.getByRole("button", { name: "Next" }).click();
    await dialog.getByLabel("Doctor name").fill("Dr Wizard");

    // Step 3 — clinical details (all optional, fill one to see it in review).
    await dialog.getByRole("button", { name: "Next" }).click();
    await dialog.getByLabel("Diagnosis").fill("Wizard-itis");

    // Step 4 — review echoes the entries, then submit.
    await dialog.getByRole("button", { name: "Next" }).click();
    await expect(dialog.getByText("Wizard-itis")).toBeVisible();
    await expect(dialog.getByText("Dr Wizard")).toBeVisible();
    await dialog.getByRole("button", { name: "Create record" }).click();

    // Landing on the record detail proves the record was created.
    await expect(page).toHaveURL(new RegExp(`/members/${memberId}/records/`));
    await expect(
      page.getByRole("heading", { name: "Doctor visit" }),
    ).toBeVisible();
    await expect(page.getByText("Wizard-itis")).toBeVisible();
    await expect(page.getByText("Dr Wizard")).toBeVisible();
  });

  test("classic form is still reachable and works", async ({ page }) => {
    const username = `e2e-classic-${Date.now()}`;
    const session = await freshSession(page, username);
    const memberId = await createMember(session, "Classic Patient");
    await page.goto(`/members/${memberId}`);

    await page.getByRole("button", { name: "New record" }).click();
    const dialog = page.getByRole("dialog", { name: "New record" });
    await dialog.getByRole("button", { name: "Classic form" }).click();

    const form = dialog.getByRole("form", { name: "New record" });
    await form.getByLabel("Type").selectOption("lab_report");
    await form.getByLabel("Doctor name").fill("Dr Classic");
    await form.getByRole("button", { name: "Create record" }).click();

    await expect(page).toHaveURL(new RegExp(`/members/${memberId}/records/`));
    await expect(
      page.getByRole("heading", { name: "Lab report" }),
    ).toBeVisible();
  });
});
