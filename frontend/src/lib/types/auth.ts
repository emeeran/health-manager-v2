export interface User {
  id: string;
  username: string;
  role: string;
}

export interface Credentials {
  username: string;
  password: string;
  /** TOTP or backup code, required once the account answers `requires_2fa`. */
  code?: string;
}

/** Sentinel returned by POST /auth/login when a 2FA code must be supplied. */
export interface Requires2fa {
  requires_2fa: true;
}

export type LoginResponse = User | Requires2fa;

export function isRequires2fa(
  response: LoginResponse,
): response is Requires2fa {
  return (
    typeof response === "object" &&
    response !== null &&
    "requires_2fa" in response &&
    response.requires_2fa === true
  );
}

/** Response of POST /auth/2fa/setup — the secret is enabled only after verify. */
export interface TwoFactorSetup {
  secret: string;
  qr_data_url: string;
  backup_codes: string[];
}
