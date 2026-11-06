import { expect, test } from "@playwright/test";
import { createMember, freshSession } from "./helpers";

test.describe("Navigation & layout", () => {
  test("unauthenticated visitors are sent to login", async ({ page }) => {
    await page.goto("/members");
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });

  test("sidebar links land on their pages", async ({ page }) => {
    await freshSession(page, `e2e-nav-${Date.now()}`);

    const cases: [string, RegExp, RegExp][] = [
      ["Members", /\/members/, /^Members$/],
      ["Providers", /\/providers/, /Providers/],
      ["Medicines", /\/medicines/, /Medicines/],
      ["Data hygiene", /\/data-hygiene/, /Data hygiene/],
      ["Chat", /\/chat/, /Chat/],
      ["AI tools", /\/ai-tools/, /AI tools/],
      ["Settings", /\/settings/, /Settings/],
    ];

    for (const [label, url, heading] of cases) {
      await page.getByRole("link", { name: label, exact: true }).click();
      await expect(page).toHaveURL(url);
      await expect(
        page.getByRole("heading", { name: heading }).first(),
      ).toBeVisible();
    }

    // Home is an exact-path link (every other link is a prefix match).
    await page.getByRole("link", { name: "Home", exact: true }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("member detail tabs switch and deep-link via ?tab=", async ({
    page,
  }) => {
    const session = await freshSession(page, `e2e-nav-tabs-${Date.now()}`);
    const memberId = await createMember(session, "Nav Tab Member");

    // Default tab is overview.
    await page.goto(`/members/${memberId}`);
    await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(
      page.getByRole("region", { name: "Member summary" }),
    ).toBeVisible();

    // Clicking a tab swaps the panel and writes ?tab=.
    const tabs = ["records", "trends", "journal", "safety", "conditions"];
    for (const tab of tabs) {
      await page
        .getByRole("tab", { name: new RegExp(`^${tab}$`, "i") })
        .click();
      await expect(page).toHaveURL(new RegExp(`tab=${tab}`));
      await expect(
        page.getByRole("tab", { name: new RegExp(`^${tab}$`, "i") }),
      ).toHaveAttribute("aria-selected", "true");
    }

    // Panel content really switches — the sections render under their tabs.
    await page.getByRole("tab", { name: "Conditions" }).click();
    await expect(
      page.getByRole("region", { name: "Condition episodes" }),
    ).toBeVisible();
    await page.getByRole("tab", { name: "Records" }).click();
    await expect(page.getByText("No records yet")).toBeVisible();

    // Deep link: ?tab= renders that tab straight away; unknown tabs fall
    // back to overview.
    await page.goto(`/members/${memberId}?tab=trends`);
    await expect(page.getByRole("tab", { name: "Trends" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByRole("heading", { name: "Trends" })).toBeVisible();

    await page.goto(`/members/${memberId}?tab=bogus`);
    await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
