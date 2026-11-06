import { apiRequest } from "../api-client";
import type {
  Credentials,
  LoginResponse,
  TwoFactorSetup,
  User,
} from "../types/auth";

export function register(credentials: Credentials): Promise<User> {
  return apiRequest<User>("/auth/register", {
    method: "POST",
    body: credentials,
  });
}

/**
 * Sign in. Returns the user on success, or `{requires_2fa: true}` (no cookies
 * set) when the account has two-factor auth and no code was supplied.
 */
export function login(credentials: Credentials): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: credentials,
  });
}

/**
 * Begin 2FA enrolment. The secret is stored server-side but stays disabled
 * until a live code is confirmed via `verify2fa`.
 */
export function setup2fa(): Promise<TwoFactorSetup> {
  return apiRequest<TwoFactorSetup>("/auth/2fa/setup", { method: "POST" });
}

/** Enable 2FA by confirming a live code from the authenticator. */
export function verify2fa(code: string): Promise<{ enabled: boolean }> {
  return apiRequest<{ enabled: boolean }>("/auth/2fa/verify", {
    method: "POST",
    body: { code },
  });
}

/** Disable 2FA; accepts a TOTP or a backup code. */
export function disable2fa(code: string): Promise<void> {
  return apiRequest<void>("/auth/2fa/disable", {
    method: "POST",
    body: { code },
  });
}

/** Rotate auth cookies. */
export function refresh(): Promise<void> {
  return apiRequest<void>("/auth/refresh", { method: "POST" });
}

export function logout(): Promise<void> {
  return apiRequest<void>("/auth/logout", { method: "POST" });
}
