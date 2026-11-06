import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { freshSession } from "./helpers";

/**
 * Accessibility smoke: axe scans of the key surfaces (login before auth,
 * home and members after). Fails on serious/critical violations; the
 * color-contrast rule is excluded until the palette passes a dedicated
 * audit — track it, don't block on it here.
 */
async function scan(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .disableRules(["color-contrast"])
    .analyze();
  return results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
}

test.describe("Accessibility (axe)", () => {
  test("login page has no serious violations", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    const violations = await scan(page);
    expect(
      violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
      "login has axe violations",
    ).toEqual([]);
  });

  test("home dashboard has no serious violations", async ({ page }) => {
    await freshSession(page, `e2e-axe-home-${Date.now()}`);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ }),
    ).toBeVisible();
    const violations = await scan(page);
    expect(
      violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
      "home has axe violations",
    ).toEqual([]);
  });

  test("members page has no serious violations", async ({ page }) => {
    await freshSession(page, `e2e-axe-members-${Date.now()}`);
    await page.goto("/members");
    await expect(page.getByRole("heading", { name: "Members" })).toBeVisible();
    const violations = await scan(page);
    expect(
      violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
      "members has axe violations",
    ).toEqual([]);
  });
});
