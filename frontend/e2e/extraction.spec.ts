import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { API, api, createMember, freshSession } from "./helpers";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.join(HERE, "fixtures", "test-medical.png");

test.skip(!existsSync(FIXTURE_PATH), "fixture image missing");

test("extraction degrades gracefully when no AI provider is available", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const session = await freshSession(page, `e2e-extract-${Date.now()}`);
  const memberId = await createMember(session, "Extract Patient");

  // Create a record to attach the extraction attempt to.
  const record = await api<{ id: string }>(
    session,
    `${API}/members/${memberId}/records`,
    {
      method: "POST",
      body: { record_type: "doctor_visit", record_date: "2026-01-15" },
    },
  );
  expect(record.status).toBe(201);
  const recordId = record.body.id;

  await page.goto(`/members/${memberId}/records/${recordId}`);

  // "Extract with AI" is a label over a hidden file input.
  await page.locator("#extract-input").setInputFiles(FIXTURE_PATH);
  await expect(page.getByText("Extracting…")).toBeVisible();

  // The e2e backend has no AI providers configured. The SSE call must
  // settle — either the backend's 503 message ("No AI provider available")
  // or, if a local provider happens to be running, a completed result.
  // What must never happen is the panel spinning forever.
  const settled = expect
    .poll(
      async () =>
        (await page.getByRole("alert").count()) > 0 ||
        (await page.getByText(/via\s/).count()) > 0,
      { timeout: 90_000, intervals: [1_000] },
    )
    .toBe(true);
  await settled;

  // Error path: the backend's own message surfaces and the panel unwinds.
  const providerError = page
    .getByRole("alert")
    .filter({ hasText: /No AI provider available/i });
  if (await providerError.isVisible().catch(() => false)) {
    await expect(providerError).toBeVisible();
  } else {
    await expect(page.getByText(/via\s/)).toBeVisible();
  }

  // The control returns to its idle state — the UI is usable again.
  await expect(page.getByText("Extracting…")).toHaveCount(0, {
    timeout: 10_000,
  });
  await expect(page.getByText("Extract with AI")).toBeVisible();
});
