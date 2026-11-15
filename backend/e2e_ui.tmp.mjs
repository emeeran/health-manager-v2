/* UI verification: login → member records tab (chips) → record detail (report, structured data). */
import { chromium } from "playwright";

const BASE = "http://localhost:3000";
const USERNAME = "friction-1794729605737";
const PASSWORD = "Friction-Pass-1!";
const MEMBER_URL = "/members/eb4e99d2-2f78-4d3d-b868-fb150f30b3fa";

const browser = await chromium.launch({ args: ["--no-sandbox"] });
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));

await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
await page.locator("#username").fill(USERNAME);
await page.locator("#password").fill(PASSWORD);
await page.locator('button:has-text("Sign in")').click();
await page.waitForURL(`${BASE}/`, { timeout: 15000 });
console.log("logged in");

await page.goto(`${BASE}${MEMBER_URL}`, { waitUntil: "networkidle" });
await page.locator('button:has-text("Records"), [role="tab"]:has-text("Records")').first().click();
await page.waitForTimeout(1200);
await page.screenshot({ path: "/tmp/e2e-shots/20-records-chips.png" });
for (const chip of ["All", "Visit to Doctor", "Lab Test"]) {
  console.log(`chip "${chip}":`, await page.locator(`button:has-text("${chip}")`).first().isVisible().catch(() => false));
}
// Filter to Lab Test → timeline should empty out (the seeded record is a visit).
await page.locator('button:has-text("Lab Test")').first().click();
await page.waitForTimeout(500);
const emptyOnLab = await page.locator('text=No records yet').first().isVisible().catch(() => false);
console.log("lab filter empties timeline:", emptyOnLab);
await page.locator('button:has-text("Visit to Doctor")').first().click();
await page.waitForTimeout(400);
await page.screenshot({ path: "/tmp/e2e-shots/21-filtered-visit.png" });

// Open the record.
await page.locator('a:has-text("Visit to Doctor")').first().click();
await page.waitForTimeout(1500);
await page.screenshot({ path: "/tmp/e2e-shots/22-record-detail.png", fullPage: true });
console.log("stored report rendered:", await page.locator('text=CONSOLIDATED CLINICAL MEDICAL REPORT').first().isVisible().catch(() => false));
console.log("structured data section:", await page.locator('text=Structured data').first().isVisible().catch(() => false));
const medPrompt = await page.locator('text=Update your medications\, button:has-text("medication")'.replace("\\,", ",")).first().isVisible().catch(() => false);
console.log("meds prompt visible:", medPrompt);
const emptyFields = await page.locator('section[aria-label="Record details"] >> text=—').count();
console.log("empty-field placeholders in details:", emptyFields);

console.log("page errors:", errors.length ? errors : "none");
await browser.close();
