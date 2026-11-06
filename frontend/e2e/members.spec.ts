import { expect, test } from "@playwright/test";
import { API, api, createMember, freshSession } from "./helpers";

test.describe("Members", () => {
  test("a member created in the form appears in the list", async ({ page }) => {
    await freshSession(page, `e2e-mem-create-${Date.now()}`);

    await page.getByRole("link", { name: "Members" }).click();
    await page.getByLabel("Full name").fill("Ada Example");
    await page.getByRole("button", { name: "Add member" }).click();

    const row = page.getByRole("listitem").filter({ hasText: "Ada Example" });
    await expect(row).toBeVisible();
    await expect(row).toContainText("self");
  });

  test("edits reach the API and show up in the UI", async ({ page }) => {
    // v2 has no member-edit screen (v1 did) — the update path is the
    // PATCH /members/{id} contract, so drive it via the API and verify the
    // UI reflects the change.
    const username = `e2e-mem-edit-${Date.now()}`;
    const session = await freshSession(page, username);
    const memberId = await createMember(session, "Rename Target");

    const res = await api<{ name: string }>(
      session,
      `${API}/members/${memberId}`,
      { method: "PATCH", body: { name: "Renamed Person", blood_group: "O+" } },
    );
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ name: "Renamed Person" });

    // Full page load: a client-side nav would mount within SWR's dedupe
    // window and serve the pre-PATCH cache indefinitely.
    await page.goto("/members");
    await page
      .getByRole("listitem")
      .filter({ hasText: "Renamed Person" })
      .getByRole("link")
      .click();
    await expect(
      page.getByRole("heading", { name: "Renamed Person" }),
    ).toBeVisible();
    await expect(page.getByText("O+", { exact: true })).toBeVisible();
  });

  test("members appear in the home family strip", async ({ page }) => {
    const session = await freshSession(page, `e2e-mem-strip-${Date.now()}`);
    const memberId = await createMember(session, "Strip Person");

    await page.goto("/");
    const strip = page.getByRole("navigation", { name: "Family members" });
    await expect(strip).toBeVisible();
    const chip = strip.getByRole("link", { name: /Strip Person/ });
    await expect(chip).toBeVisible();
    await chip.click();
    await expect(page).toHaveURL(new RegExp(`/members/${memberId}`));
  });

  test("several members are all listed", async ({ page }) => {
    const session = await freshSession(page, `e2e-mem-many-${Date.now()}`);
    await createMember(session, "List Person A");
    await createMember(session, "List Person B");

    await page.goto("/members");
    const list = page.getByRole("list");
    await expect(
      list.getByRole("link", { name: /List Person A/ }),
    ).toBeVisible();
    await expect(
      list.getByRole("link", { name: /List Person B/ }),
    ).toBeVisible();
  });
});
