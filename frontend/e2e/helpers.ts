import { createHmac } from "node:crypto";
import {
  expect,
  request,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

// The vite dev server proxies /api to the e2e backend; the API context talks
// to it directly through the browser-origin port so relative paths work.
export const API = "/api/v1";
export const PASSWORD = "e2e-password-123";
const FRONT_PORT = process.env.E2E_FRONT_PORT ?? "3000";

// Mirrors the SECRET_KEY set for the backend in playwright.config.ts. The
// notifications spec reuses it so a helper process can encrypt/decrypt the
// same columns the server writes.
export const BACKEND_SECRET_KEY =
  "e2e-secret-key-not-used-in-prod-32-bytes-min";

export interface Session {
  ctx: APIRequestContext;
  username: string;
}

/**
 * A fresh unauthenticated API context. Seeding calls run here — NOT via
 * in-page fetch — because the dev server occasionally reloads the page
 * mid-test (service-worker claim, dep re-optimization), which would kill
 * in-flight evaluates and could duplicate non-idempotent POSTs.
 */
export async function newApiContext(): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: `http://localhost:${FRONT_PORT}`,
  });
}

/** Register a user through the API; 409 (already taken) is fine. */
export async function registerViaApi(
  ctx: APIRequestContext,
  username: string,
): Promise<void> {
  const res = await ctx.post(`${API}/auth/register`, {
    data: { username, password: PASSWORD },
    failOnStatusCode: false,
  });
  if (!res.ok() && res.status() !== 409) {
    throw new Error(`register ${username} failed: ${res.status()}`);
  }
}

/**
 * Register + sign in a brand-new user on its own API context. Auth lives as
 * cookies on that context; `applySession` copies them into a browser context.
 */
export async function createSession(username: string): Promise<Session> {
  const ctx = await newApiContext();
  await registerViaApi(ctx, username);
  const res = await ctx.post(`${API}/auth/login`, {
    data: { username, password: PASSWORD },
  });
  if (!res.ok()) throw new Error(`login ${username} failed: ${res.status()}`);
  return { ctx, username };
}

export interface ApiResult<T = unknown> {
  status: number;
  body: T;
}

/** Authenticated JSON call on a session's API context. */
export async function api<T = unknown>(
  session: Session,
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<ApiResult<T>> {
  const res = await session.ctx.fetch(path, {
    method: init.method ?? "GET",
    headers:
      init.body !== undefined
        ? { "Content-Type": "application/json" }
        : undefined,
    data: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  let body: T = null as T;
  try {
    body = (await res.json()) as T;
  } catch {
    // 204s and empty bodies are fine.
  }
  return { status: res.status(), body };
}

/** Copy a session's auth cookies into the browser context. */
export async function applySession(
  page: Page,
  session: Session,
): Promise<void> {
  const { cookies } = await session.ctx.storageState();
  await page.context().addCookies(cookies);
}

/** Create a session, sign the browser in, and land on the home page. */
export async function freshSession(
  page: Page,
  username: string,
): Promise<Session> {
  const session = await createSession(username);
  await applySession(page, session);
  await page.goto("/");
  // The account button shows the username only once /auth/me has succeeded —
  // proof the browser session really works before the test body starts.
  await expect(page.getByRole("button", { name: username })).toBeVisible({
    timeout: 15_000,
  });
  return session;
}

/** Register + sign in through the real UI form (starts logged out). */
export async function registerViaUi(
  page: Page,
  username: string,
): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL("/");
}

/** Sign in through the real UI form. */
export async function loginViaUi(page: Page, username: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
}

/** Create a family member via the API and return its id. */
export async function createMember(
  session: Session,
  name: string,
  relationship = "self",
): Promise<string> {
  const res = await api<{ id: string }>(session, `${API}/members`, {
    method: "POST",
    body: { name, relationship },
  });
  if (res.status !== 201) {
    throw new Error(`create member ${name} failed: ${res.status}`);
  }
  return res.body.id;
}

const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(input: string): Buffer {
  const clean = input.toUpperCase().replace(/=+$/, "");
  const bytes: number[] = [];
  let bits = 0;
  let value = 0;
  for (const ch of clean) {
    const idx = BASE32.indexOf(ch);
    if (idx === -1) continue;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(bytes);
}

/**
 * RFC 6238 TOTP (SHA-1, 30 s step, 6 digits) — the same parameters the
 * backend's pyotp TOTP defaults use. Lets the auth spec act as an
 * authenticator without extra npm dependencies.
 */
export function totp(secret: string, atMs: number = Date.now()): string {
  const step = 30;
  const counter = Math.floor(atMs / 1000 / step);
  const msg = Buffer.alloc(8);
  msg.writeUInt32BE(Math.floor(counter / 2 ** 32), 0);
  msg.writeUInt32BE(counter % 2 ** 32, 4);
  const hmac = createHmac("sha1", base32Decode(secret)).update(msg).digest();
  const offset = hmac[hmac.length - 1] & 0xf;
  const binary =
    ((hmac[offset] & 0x7f) << 24) |
    (hmac[offset + 1] << 16) |
    (hmac[offset + 2] << 8) |
    hmac[offset + 3];
  return String(binary % 1_000_000).padStart(6, "0");
}
