import { expect, test } from "@playwright/test";
import {
  API,
  PASSWORD,
  api,
  applySession,
  createSession,
  loginViaUi,
  newApiContext,
  registerViaApi,
  registerViaUi,
  totp,
} from "./helpers";

test.describe("Authentication", () => {
  test("register signs the new account in and lands on home", async ({
    page,
  }) => {
    await registerViaUi(page, `e2e-auth-reg-${Date.now()}`);
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("link", { name: "Home" })).toBeVisible();
  });

  test("wrong password is rejected with an inline error", async ({ page }) => {
    const username = `e2e-auth-bad-${Date.now()}`;
    const ctx = await newApiContext();
    await registerViaApi(ctx, username);

    await page.goto("/login");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Password").fill("definitely-wrong-pass");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toContainText(/invalid/i);
    await expect(page).toHaveURL(/\/login/);
  });

  test("logout clears the session and protected pages bounce to login", async ({
    page,
  }) => {
    const session = await createSession(`e2e-auth-out-${Date.now()}`);
    await applySession(page, session);
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: session.username }),
    ).toBeVisible();

    // Account menu → Logout.
    await page.getByRole("button", { name: session.username }).click();
    await page.getByRole("menuitem", { name: "Logout" }).click();
    await expect(page).toHaveURL(/\/login/);

    // The access cookie is gone; the auth guard sends us back to login.
    await page.goto("/members");
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });

  test("login works after signing out", async ({ page }) => {
    const session = await createSession(`e2e-auth-relog-${Date.now()}`);
    await applySession(page, session);
    await page.goto("/");
    await page.getByRole("button", { name: session.username }).click();
    await page.getByRole("menuitem", { name: "Logout" }).click();
    await expect(page).toHaveURL(/\/login/);

    await loginViaUi(page, session.username);
    await expect(page.getByRole("link", { name: "Home" })).toBeVisible();
  });

  test("2FA: enabling TOTP makes login require the one-time code", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const session = await createSession(`e2e-auth-2fa-${Date.now()}`);

    // Enable TOTP through the API: setup mints the secret, verify confirms a
    // live code and flips the account to totp_enabled.
    const setup = await api<{ secret: string }>(
      session,
      `${API}/auth/2fa/setup`,
      {
        method: "POST",
      },
    );
    expect(setup.status).toBe(200);
    const { secret } = setup.body;
    expect(secret).toBeTruthy();

    const verify = await api(session, `${API}/auth/2fa/verify`, {
      method: "POST",
      body: { code: totp(secret) },
    });
    expect(verify.status).toBe(200);
    expect(verify.body).toMatchObject({ enabled: true });

    // Password alone no longer completes sign-in: the form moves to the
    // code step instead of navigating.
    await page.goto("/login");
    await page.getByLabel("Username").fill(session.username);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(
      page.getByRole("heading", { name: "Two-factor code" }),
    ).toBeVisible();
    await expect(page).toHaveURL(/\/login/);

    // A wrong code is rejected and keeps the account at the code step.
    await page.getByLabel("Code").fill("000000");
    await page.getByRole("button", { name: "Verify & sign in" }).click();
    await expect(page.getByRole("alert")).toContainText(/invalid/i);
    await expect(page).toHaveURL(/\/login/);

    // The live TOTP code completes the sign-in.
    await page.getByLabel("Code").fill(totp(secret));
    await page.getByRole("button", { name: "Verify & sign in" }).click();
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("link", { name: "Home" })).toBeVisible();
  });

  test("2FA can be disabled again with a valid code", async () => {
    const session = await createSession(`e2e-auth-2fa-off-${Date.now()}`);

    const setup = await api<{ secret: string }>(
      session,
      `${API}/auth/2fa/setup`,
      {
        method: "POST",
      },
    );
    const { secret } = setup.body;
    const verify = await api(session, `${API}/auth/2fa/verify`, {
      method: "POST",
      body: { code: totp(secret) },
    });
    expect(verify.status).toBe(200);

    // Password-only login now answers requires_2fa (still 200 — no cookies
    // are issued until the code is presented).
    const gated = await api<{ requires_2fa?: boolean }>(
      session,
      `${API}/auth/login`,
      {
        method: "POST",
        body: { username: session.username, password: PASSWORD },
      },
    );
    expect(gated.status).toBe(200);
    expect(gated.body).toMatchObject({ requires_2fa: true });

    const off = await api(session, `${API}/auth/2fa/disable`, {
      method: "POST",
      body: { code: totp(secret) },
    });
    expect(off.status).toBe(204);

    const open = await api<{ requires_2fa?: boolean; username?: string }>(
      session,
      `${API}/auth/login`,
      {
        method: "POST",
        body: { username: session.username, password: PASSWORD },
      },
    );
    expect(open.status).toBe(200);
    expect(open.body).toEqual(
      expect.not.objectContaining({ requires_2fa: true }),
    );
    expect(open.body).toMatchObject({ username: session.username });
  });
});
