import { expect, test } from "@playwright/test";
import { createMember, freshSession } from "./helpers";

test("deleting a member asks for confirmation and removes them", async ({
  page,
}) => {
  const session = await freshSession(page, `e2e-del-${Date.now()}`);
  const name = `Doomed Person ${Date.now() % 100000}`;
  await createMember(session, name);

  await page.goto("/members");
  const row = page.getByRole("link", { name: new RegExp(name) });
  await expect(row).toBeVisible();

  // Dismissing the native confirm() keeps the member.
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain(`Remove ${name}`);
    void dialog.dismiss();
  });
  await page.getByRole("button", { name: `Delete ${name}` }).click();
  await expect(row).toBeVisible();

  // Accepting deletes the member; the list revalidates without them.
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: `Delete ${name}` }).click();
  await expect(page.getByRole("link", { name: new RegExp(name) })).toHaveCount(
    0,
    { timeout: 10_000 },
  );

  // And the API agrees they are gone.
  await page.reload();
  await expect(page.getByRole("link", { name: new RegExp(name) })).toHaveCount(
    0,
  );
});
