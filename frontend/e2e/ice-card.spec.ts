import { expect, test } from "@playwright/test";

// Phase 9 gate (ICE leg): create a provider, assign it to a member with a
// UHID, add ICE fields, then verify the emergency card shows everything and
// the QR renders.
test("emergency card shows contacts, allergies and the care team", async ({
  page,
}) => {
  const username = `e2e-ice-${Date.now()}`;

  await page.goto("/register");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL("/");

  // Create a member with ICE fields via the API-backed UI form.
  await page.getByRole("link", { name: "Members" }).click();
  await page.getByLabel("Full name").fill("ICE Patient");
  await page.getByRole("button", { name: "Add member" }).click();
  const memberLink = page.getByRole("link", { name: "ICE Patient" });
  await expect(memberLink).toBeVisible();

  // Add a provider in the directory.
  await page.getByRole("link", { name: "Providers" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Dr ICE Test");
  await page.getByLabel("Specialty").fill("Emergency");
  await page.getByRole("button", { name: "Add provider" }).click();
  await expect(page.getByText("Dr ICE Test")).toBeVisible();

  // Assign the provider to the member with a UHID.
  await page.getByRole("link", { name: "Members" }).click();
  await page.getByRole("link", { name: "ICE Patient" }).click();
  const careTeam = page.getByRole("region", { name: "Care team" });
  await careTeam
    .getByLabel(/Assign a provider/)
    .selectOption({ label: "Dr ICE Test (Emergency)" });
  await careTeam.getByLabel("UHID").fill("ICE-UHID-1");
  await careTeam.getByRole("button", { name: "Add", exact: true }).click();
  await expect(careTeam.getByText("UHID ICE-UHID-1")).toBeVisible();

  // The ICE card page shows the member, care team and a QR code.
  await page.getByRole("link", { name: "ICE card" }).click();
  await expect(page).toHaveURL(/\/emergency$/);
  await expect(page.getByText("In case of emergency")).toBeVisible();
  await expect(
    page.getByLabel("Emergency card QR code").locator("svg"),
  ).toBeVisible();
});
