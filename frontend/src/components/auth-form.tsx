import { Loader2, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AppLogo } from "./layout/app-logo";
import {
  isRequires2fa,
  type Credentials,
  type LoginResponse,
  type User,
} from "../lib/types/auth";

interface AuthFormProps {
  mode: "login" | "register";
  onSubmit: (credentials: Credentials) => Promise<LoginResponse | User>;
}

/** Centered card form shared by the Login and Register pages. */
export function AuthForm({ mode, onSubmit }: AuthFormProps) {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // Set once the backend answers `requires_2fa`: the next submit re-sends the
  // same credentials plus the one-time code to POST /auth/login/2fa.
  const [awaitingCode, setAwaitingCode] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const credentials: Credentials = awaitingCode
        ? { username, password, code }
        : { username, password };
      const result = await onSubmit(credentials);
      if (isRequires2fa(result)) {
        setAwaitingCode(true);
        return;
      }
      navigate("/", { replace: true });
    } catch (err) {
      // A rejected code leaves the account in the 2FA step; keep asking.
      if (awaitingCode) setCode("");
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-8 shadow-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <AppLogo className="size-10 rounded-xl" />
          <h1 className="text-lg font-semibold">
            {awaitingCode
              ? "Two-factor code"
              : mode === "login"
                ? "Sign in"
                : "Create an account"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Family Health Manager v2
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {awaitingCode ? (
            <>
              <p className="flex items-start gap-2 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                <ShieldCheck
                  className="mt-0.5 size-4 shrink-0 text-primary"
                  aria-hidden
                />
                Enter a 6-digit code from your authenticator app, or one of your
                backup codes.
              </p>
              <div className="space-y-1.5">
                <label htmlFor="code" className="text-sm font-medium">
                  Code
                </label>
                <input
                  id="code"
                  name="code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="123456"
                  required
                  autoFocus
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            </>
          ) : (
            <>
              <div className="space-y-1.5">
                <label htmlFor="username" className="text-sm font-medium">
                  Username
                </label>
                <input
                  id="username"
                  name="username"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="password" className="text-sm font-medium">
                  Password
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            </>
          )}

          {error && (
            <p
              role="alert"
              className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {submitting && (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            )}
            {awaitingCode
              ? "Verify & sign in"
              : mode === "login"
                ? "Sign in"
                : "Create account"}
          </button>
        </form>

        {!awaitingCode && (
          <p className="mt-6 text-center text-sm text-muted-foreground">
            {mode === "login" ? (
              <>
                No account yet?{" "}
                <Link
                  to="/register"
                  className="font-medium text-primary hover:underline"
                >
                  Register
                </Link>
              </>
            ) : (
              <>
                Already registered?{" "}
                <Link
                  to="/login"
                  className="font-medium text-primary hover:underline"
                >
                  Sign in
                </Link>
              </>
            )}
          </p>
        )}
      </div>
    </div>
  );
}
