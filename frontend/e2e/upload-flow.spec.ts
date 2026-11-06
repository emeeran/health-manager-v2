import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { createMember, freshSession } from "./helpers";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.join(HERE, "fixtures", "test-medical.png");

test.skip(!existsSync(FIXTURE_PATH), "fixture image missing");

test("upload an attachment to a new record", async ({ page }) => {
  const username = `e2e-upload-${Date.now()}`;
  const session = await freshSession(page, username);
  const memberId = await createMember(session, "Upload Patient");

  // Open the record modal and take the classic single form.
  await page.goto(`/members/${memberId}`);
  await page.getByRole("button", { name: "New record" }).click();
  const dialog = page.getByRole("dialog", { name: "New record" });
  await dialog.getByRole("button", { name: "Classic form" }).click();
  const form = dialog.getByRole("form", { name: "New record" });
  await form.getByLabel("Type").selectOption("doctor_visit");
  await form.getByLabel("Doctor name").fill("Dr. E2E");
  await form.getByRole("button", { name: "Create record" }).click();

  // Record detail: upload the fixture image.
  await expect(page).toHaveURL(new RegExp(`/members/${memberId}/records/`));
  await expect(
    page.getByRole("heading", { name: "Doctor visit" }),
  ).toBeVisible();
  await page.getByLabel("Choose files").setInputFiles(FIXTURE_PATH);

  const attachmentRow = page.getByRole("button", {
    name: /test-medical\.png/,
  });
  await expect(attachmentRow).toBeVisible();

  // Open the inline viewer; the image preview renders.
  await attachmentRow.click();
  await expect(
    page.getByRole("img", { name: "test-medical.png" }),
  ).toBeVisible();
});
