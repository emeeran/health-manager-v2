import { expect, test } from "@playwright/test";
import { createMember, freshSession } from "./helpers";

test("home dashboard renders after login", async ({ page }) => {
  const username = `e2e-smoke-${Date.now()}`;
  const session = await freshSession(page, username);
  await createMember(session, "Smoke Patient");

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ }),
  ).toBeVisible();
  await expect(page.getByText(/1 member/)).toBeVisible();

  // Family strip shows the member; score cards section is present.
  const strip = page.getByRole("navigation", { name: "Family members" });
  await expect(
    strip.getByRole("link", { name: /Smoke Patient/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Health overview" }),
  ).toBeVisible();
  await expect(
    page.getByRole("group", { name: "Quick actions" }),
  ).toBeVisible();
});

test("/ai-tools hub renders its tool cards", async ({ page }) => {
  await freshSession(page, `e2e-smoke-ai-${Date.now()}`);

  await page.goto("/ai-tools");
  await expect(page.getByRole("heading", { name: "AI tools" })).toBeVisible();

  // Card grid: a known tool card plus its group headings.
  await expect(
    page.getByRole("link", { name: /AI health insight/ }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Drug interactions/ }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
});
