import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import {
  API,
  BACKEND_SECRET_KEY,
  api,
  createMember,
  freshSession,
} from "./helpers";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BACKEND_DIR = path.resolve(HERE, "..", "..", "backend");

/**
 * Notifications have no creation endpoint on purpose — they are minted by
 * the backend's own jobs. To seed one deterministically we create an
 * out-of-range blood-pressure reading via the API, then run the exact job
 * the scheduler runs (`jobs.detect_anomalies`) as a one-shot against the
 * same database and SECRET_KEY. This is the same code path production uses,
 * just without waiting out the 6-hour cadence.
 */
function runAnomalyJob(): void {
  execFileSync(
    "uv",
    [
      "run",
      "python",
      "-c",
      "import asyncio; from app.core import jobs; print(asyncio.run(jobs.detect_anomalies()))",
    ],
    {
      cwd: BACKEND_DIR,
      env: {
        ...process.env,
        SECRET_KEY: BACKEND_SECRET_KEY,
        DATABASE_URL: "sqlite+aiosqlite:///./data/e2e-test.db",
        APP_ENV: "development",
      },
      timeout: 120_000,
    },
  );
}

test("bell shows unread state and the panel marks it read", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const session = await freshSession(page, `e2e-notif-${Date.now()}`);

  // Seed: an anomalous reading for a fresh member, then the backend job
  // turns it into a notification for this household.
  const memberId = await createMember(
    session,
    `BP Patient ${Date.now() % 100000}`,
  );
  const vital = await api(session, `${API}/members/${memberId}/vitals`, {
    method: "POST",
    body: {
      vital_type: "blood_pressure",
      value_num: 190,
      value_secondary: 115,
      unit: "mmHg",
      measured_at: new Date().toISOString(),
    },
  });
  expect(vital.status).toBe(201);

  runAnomalyJob();

  // The bell's SWR cache was fetched before the notification existed —
  // reload so the unread count is fetched fresh.
  await page.reload();

  // The bell advertises the unread count and shows the badge.
  const bell = page.getByRole("button", { name: /Notifications \(1 unread\)/ });
  await expect(bell).toBeVisible({ timeout: 15_000 });

  await bell.click();
  const panel = page.getByRole("menu").filter({ hasText: "Notifications" });
  await expect(panel).toBeVisible();
  await expect(
    panel.getByText(/Vital anomaly: BP Patient.*out of range/),
  ).toBeVisible();

  // Clicking the item marks it read; the badge and unread count clear.
  await panel.getByRole("menuitem").first().click();
  await expect(
    page.getByRole("button", { name: /^Notifications$/ }),
  ).toBeVisible({ timeout: 15_000 });
  const unread = await api<{ unread: number }>(
    session,
    `${API}/notifications/unread-count`,
  );
  expect(unread.body).toMatchObject({ unread: 0 });
});
