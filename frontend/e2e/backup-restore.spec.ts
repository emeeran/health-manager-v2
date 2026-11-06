import { rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { API, api, freshSession } from "./helpers";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RESTORE_REQUEST = path.resolve(
  HERE,
  "..",
  "..",
  "backend",
  "data",
  ".restore-request",
);

test.describe("Backup & restore", () => {
  test("create, download and request a restore from Settings → Data", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    await freshSession(page, `e2e-backup-${Date.now()}`);

    await page.getByRole("link", { name: "Settings" }).click();
    await page.getByRole("tab", { name: "Data" }).click();
    const section = page.getByRole("region", { name: "Backup & restore" });
    await expect(section).toBeVisible();

    // Create: the API responds with the filename and the UI confirms it.
    await section.getByRole("button", { name: "Create backup" }).click();
    const notice = section.getByRole("status");
    await expect(notice).toContainText("Backup created:", { timeout: 30_000 });
    const filename = (await notice.textContent())
      ?.replace("Backup created: ", "")
      .trim();
    expect(filename).toMatch(/^backup_\d{8}_\d{6}\.tar\.gz\.enc$/);

    // Download: the created row's link yields a non-empty file.
    const row = section.getByRole("row").filter({ hasText: filename });
    await expect(row).toBeVisible();
    const downloadPromise = page.waitForEvent("download", { timeout: 30_000 });
    await row.getByRole("link", { name: "Download" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(filename);

    // Restore: confirm dialog, then the router's 202 message surfaces.
    page.once("dialog", (dialog) => {
      expect(dialog.message()).toContain(filename);
      void dialog.accept();
    });
    await row.getByRole("button", { name: "Restore" }).click();
    await expect(
      section.getByText(
        "Restore queued. The system service will restart the app.",
      ),
    ).toBeVisible();

    // The request marker is a dev-filesystem artefact — clean it up so no
    // restore pipeline ever picks up an e2e request.
    rmSync(RESTORE_REQUEST, { force: true });
  });

  test("restore-request rejects malformed filenames per the API contract", async ({
    page,
  }) => {
    const session = await freshSession(page, `e2e-backup-api-${Date.now()}`);

    const bad = await api(session, `${API}/backup/restore-request`, {
      method: "POST",
      body: { filename: "../../etc/passwd" },
    });
    expect(bad.status).toBe(400);

    const missing = await api(session, `${API}/backup/restore-request`, {
      method: "POST",
      body: { filename: "backup_19700101_000000.tar.gz.enc" },
    });
    expect(missing.status).toBe(404);
  });
});
