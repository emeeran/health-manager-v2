import {
  Check,
  Copy,
  KeyRound,
  Loader2,
  ShieldCheck,
  ShieldOff,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import QRCode from "react-qr-code";
import { disable2fa, setup2fa, verify2fa } from "../../lib/api/auth";
import type { TwoFactorSetup, User } from "../../lib/types/auth";
import { INPUT_CLASS } from "../../lib/utils";

/**
 * Two-factor enrolment and removal.
 *
 * The backend exposes no "is 2FA enabled" status endpoint, so `enabled` only
 * tracks what happens in this session: after setup is confirmed the panel
 * switches to the disable flow, and after disabling back to setup.
 */
export function TwoFactorSection() {
  const [enabled, setEnabled] = useState(false);

  return (
    <section
      aria-label="Two-factor authentication"
      className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <KeyRound className="size-4 text-primary" aria-hidden />
        Two-factor authentication
      </h2>
      {enabled ? (
        <DisablePanel onDisabled={() => setEnabled(false)} />
      ) : (
        <SetupPanel onEnabled={() => setEnabled(true)} />
      )}
    </section>
  );
}

function SetupPanel({ onEnabled }: { onEnabled: () => void }) {
  const { data: me } = useSWR<User>("/auth/me");
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function begin() {
    setBusy(true);
    setError(null);
    try {
      setSetup(await setup2fa());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await verify2fa(code);
      onEnabled();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not verify that code. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function copySecret() {
    if (!setup) return;
    await navigator.clipboard.writeText(setup.secret);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (!setup) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Add a second factor with any TOTP authenticator app (Aegis, 1Password,
          Google Authenticator). You'll confirm a live code to switch it on, and
          receive one-time backup codes for when the phone is lost.
        </p>
        <button
          type="button"
          onClick={() => void begin()}
          disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <ShieldCheck className="size-4" aria-hidden />
          )}
          Set up 2FA
        </button>
        <FormError error={error} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ol className="space-y-3 text-sm">
        <li className="space-y-2">
          <p className="font-medium">1. Scan with your authenticator app</p>
          <div className="w-fit rounded-lg border border-border bg-white p-2">
            <span aria-label="Two-factor QR code">
              <QRCode
                value={otpauthUri(setup.secret, me?.username)}
                size={160}
              />
            </span>
          </div>
          <p className="text-muted-foreground">
            Can't scan? Enter the secret manually:{" "}
            <button
              type="button"
              onClick={() => void copySecret()}
              className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline"
            >
              {setup.secret}
              {copied ? (
                <Check className="size-3" aria-hidden />
              ) : (
                <Copy className="size-3" aria-hidden />
              )}
            </button>
          </p>
        </li>
        <li className="space-y-2">
          <p className="font-medium">
            2. Save your backup codes somewhere safe
          </p>
          <ul className="grid w-fit grid-cols-2 gap-x-6 gap-y-1 rounded-lg border border-border bg-background px-4 py-3 font-mono text-xs">
            {setup.backup_codes.map((backupCode) => (
              <li key={backupCode}>{backupCode}</li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            Each code works once instead of a TOTP. They won't be shown again.
          </p>
        </li>
      </ol>

      <form onSubmit={confirm} className="flex items-end gap-2">
        <label className="flex-1 space-y-1.5 text-sm font-medium">
          3. Enter the current 6-digit code
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456"
            required
            className={INPUT_CLASS}
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
          Confirm & enable
        </button>
      </form>
      <FormError error={error} />
    </div>
  );
}

function DisablePanel({ onDisabled }: { onDisabled: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!window.confirm("Turn off two-factor authentication?")) return;
    setBusy(true);
    setError(null);
    try {
      await disable2fa(code);
      onDisabled();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not disable 2FA.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <ShieldCheck className="size-4 text-primary" aria-hidden />
        Two-factor authentication is active on your account.
      </p>
      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <label className="flex-1 space-y-1.5 text-sm font-medium">
          Code (TOTP or backup code)
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456 or backup code"
            required
            className={INPUT_CLASS}
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <ShieldOff className="size-4" aria-hidden />
          )}
          Disable 2FA
        </button>
      </form>
      <FormError error={error} />
    </div>
  );
}

/**
 * Standard `otpauth://` URI the authenticator encodes from a scan. Issuer and
 * account name are cosmetic — the secret is what matters.
 */
function otpauthUri(secret: string, username?: string): string {
  const label = encodeURIComponent(
    `Family Health Manager:${username ?? "account"}`,
  );
  const issuer = encodeURIComponent("Family Health Manager");
  return `otpauth://totp/${label}?secret=${secret}&issuer=${issuer}`;
}

function FormError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p
      role="alert"
      className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
    >
      {error}
    </p>
  );
}
