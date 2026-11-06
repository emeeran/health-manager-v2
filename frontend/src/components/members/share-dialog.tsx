import { Check, Copy, Link2, Loader2, Share2, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { createShareLink, revokeShareLink } from "../../lib/api/share-links";
import { useEscClose } from "../../hooks/use-esc-close";
import type { ShareLinkCreated, ShareLinkSummary } from "../../lib/types/share";

const EXPIRY_OPTIONS = [1, 7, 14, 30, 90] as const;

export function ShareDialog({
  memberId,
  memberName,
  onClose,
}: {
  memberId: string;
  memberName: string;
  onClose: () => void;
}) {
  const {
    data: links,
    isLoading,
    mutate,
  } = useSWR<ShareLinkSummary[]>(
    memberId ? `/members/${memberId}/share-links` : null,
  );
  const [expiresDays, setExpiresDays] = useState<number>(7);
  const [created, setCreated] = useState<ShareLinkCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Escape closes, matching a native dialog (routed through the global
  // stack so only the topmost overlay reacts).
  useEscClose(true, onClose);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      setCreated(await createShareLink(memberId, expiresDays));
      void mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create link.");
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(linkId: string) {
    if (
      !window.confirm("Revoke this share link? Anyone holding it loses access.")
    )
      return;
    setRevokingId(linkId);
    setError(null);
    try {
      await revokeShareLink(memberId, linkId);
      await mutate();
    } catch {
      setError("Revoke failed.");
    } finally {
      setRevokingId(null);
    }
  }

  async function copyToken() {
    if (!created) return;
    await navigator.clipboard.writeText(shareUrl(created.token_shown_once));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const active = (links ?? []).filter((link) => !link.revoked);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Share ${memberName}'s emergency summary`}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl border border-border bg-card p-5 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Share2 className="size-4 text-primary" aria-hidden />
            Share emergency summary
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>

        {created ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              This link works until {formatDate(created.expires_at)} and shows{" "}
              {memberName}'s medications, allergies and conditions — no sign-in
              needed.
            </p>
            <div className="rounded-lg border border-border bg-background p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Share link — shown only this once
              </p>
              <p className="mt-1.5 wrap-anywhere break-all font-mono text-xs">
                {shareUrl(created.token_shown_once)}
              </p>
              <button
                type="button"
                onClick={() => void copyToken()}
                className="mt-3 flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                {copied ? (
                  <Check className="size-4" aria-hidden />
                ) : (
                  <Copy className="size-4" aria-hidden />
                )}
                {copied ? "Copied" : "Copy link"}
              </button>
            </div>
            <button
              type="button"
              onClick={() => setCreated(null)}
              className="text-sm font-medium text-primary hover:underline"
            >
              Create another link
            </button>
          </div>
        ) : (
          <form onSubmit={handleCreate} className="space-y-4">
            <label className="block space-y-1.5 text-sm font-medium">
              Link expires after
              <select
                value={expiresDays}
                onChange={(e) => setExpiresDays(Number(e.target.value))}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              >
                {EXPIRY_OPTIONS.map((days) => (
                  <option key={days} value={days}>
                    {days} {days === 1 ? "day" : "days"}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-sm text-muted-foreground">
              Anyone with the link can view a read-only emergency summary —
              never the full records. Copy it and share it with the treating
              clinician.
            </p>
            <button
              type="submit"
              disabled={creating}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {creating ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <Link2 className="size-4" aria-hidden />
              )}
              Create link
            </button>
          </form>
        )}

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {error}
          </p>
        )}

        <div className="mt-6 border-t border-border pt-4">
          <h3 className="text-sm font-semibold">Active links</h3>
          {isLoading ? (
            <p className="mt-2 text-sm text-muted-foreground">Loading…</p>
          ) : active.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">
              No active share links.
            </p>
          ) : (
            <ul className="mt-2 space-y-2">
              {active.map((link) => (
                <li
                  key={link.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2"
                >
                  <div className="text-sm">
                    <p>Expires {formatDate(link.expires_at)}</p>
                    <p className="text-xs text-muted-foreground">
                      Created {formatDate(link.created_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRevoke(link.id)}
                    disabled={revokingId === link.id}
                    className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
                  >
                    {revokingId === link.id ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden />
                    ) : (
                      <Trash2 className="size-3.5" aria-hidden />
                    )}
                    Revoke
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function shareUrl(token: string): string {
  return `${window.location.origin}/public/share/${encodeURIComponent(token)}`;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
}
