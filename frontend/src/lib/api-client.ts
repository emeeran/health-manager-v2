const BASE_URL = "/api/v1";
const TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  /** HTTP status, or 0 for network/timeout failures. */
  readonly status: number;
  /** Raw `detail` field from the FastAPI error body (string or list). */
  readonly detail: unknown;

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? extractMessage(detail) ?? `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function isServerError(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.status === 0 || error.status >= 500)
  );
}

function extractMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map(extractMessage)
      .filter((part): part is string => !!part);
    if (parts.length > 0) return parts.join("; ");
    return undefined;
  }
  if (detail !== null && typeof detail === "object" && "msg" in detail) {
    return String((detail as { msg: unknown }).msg);
  }
  return undefined;
}

export interface RequestOptions {
  method?: string;
  /** JSON-serializable request body. */
  body?: unknown;
  signal?: AbortSignal;
}

/** Single-flight refresh: concurrent 401s share one POST /auth/refresh. */
let refreshInFlight: Promise<boolean> | null = null;

function refreshOnce(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      return response.ok;
    } catch {
      return false;
    } finally {
      queueMicrotask(() => {
        refreshInFlight = null;
      });
    }
  })();
  return refreshInFlight;
}

function redirectToLogin(): void {
  if (!window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
  }
}

interface InternalOptions extends RequestOptions {
  /** Guards against infinite refresh/retry loops. */
  retried?: boolean;
}

async function parseBody<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(response.status, text);
  }
}

async function attempt<T>(path: string, options: InternalOptions): Promise<T> {
  const { method = "GET", body } = options;
  // 30s timeout, or the caller's signal combined with it when one is given.
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  const signal = options.signal
    ? AbortSignal.any([options.signal, timeout])
    : timeout;

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      credentials: "include",
      headers:
        body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: signal ?? timeout,
    });
  } catch (error) {
    throw new ApiError(
      0,
      undefined,
      error instanceof Error ? error.message : "Network error",
    );
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      const parsed = await parseBody<unknown>(response);
      detail =
        parsed !== null && typeof parsed === "object" && "detail" in parsed
          ? (parsed as { detail: unknown }).detail
          : parsed;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      detail = undefined;
    }
    throw new ApiError(response.status, detail);
  }

  return parseBody<T>(response);
}

/**
 * Perform an authenticated API request against `/api/v1`.
 *
 * On a 401 for any non-`/auth/` path, runs a single-flight
 * `POST /auth/refresh` and retries the original request once; if the retry
 * still fails, redirects to /login.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  try {
    return await attempt<T>(path, options);
  } catch (error) {
    const canRefresh =
      error instanceof ApiError &&
      error.status === 401 &&
      !path.startsWith("/auth/") &&
      !(options as InternalOptions).retried;
    if (!canRefresh) throw error;

    const refreshed = await refreshOnce();
    if (!refreshed) {
      redirectToLogin();
      throw error;
    }
    try {
      return await attempt<T>(path, { ...options, retried: true });
    } catch (retryError) {
      if (retryError instanceof ApiError && retryError.status === 401)
        redirectToLogin();
      throw retryError;
    }
  }
}
