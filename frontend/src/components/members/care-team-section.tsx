import { Loader2, Stethoscope, Trash2, UserRoundPlus } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import {
  assignProvider,
  listAssignments,
  listProviders,
  unassignProvider,
} from "../../lib/api/providers";
import type { ProviderAssignment } from "../../lib/types/provider";

/**
 * Member ↔ provider assignments (care team) with per-hospital UHIDs.
 * Providers live in the household directory (/providers).
 */
export function CareTeamSection({ memberId }: { memberId: string }) {
  const {
    data: assignments,
    isLoading,
    mutate,
  } = useSWR(memberId ? `members/${memberId}/providers` : null, () =>
    listAssignments(memberId),
  );
  const { data: providers } = useSWR("/providers", listProviders);
  const [providerId, setProviderId] = useState("");
  const [uhid, setUhid] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    if (!providerId) return;
    setBusy(true);
    setError(null);
    try {
      await assignProvider(memberId, providerId, uhid || undefined);
      setProviderId("");
      setUhid("");
      await mutate();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not assign provider.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function remove(assignment: ProviderAssignment) {
    await unassignProvider(memberId, assignment.id);
    await mutate();
  }

  return (
    <section
      aria-label="Care team"
      className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Stethoscope className="size-4 text-primary" aria-hidden />
        Care team
      </h2>

      {isLoading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" aria-hidden /> Loading…
        </p>
      )}

      {assignments && assignments.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {assignments.map((assignment) => (
            <li
              key={assignment.id}
              className="flex items-center gap-3 px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {assignment.provider_name}
                </p>
                <p className="text-xs text-muted-foreground">
                  {[assignment.specialty, assignment.hospital]
                    .filter(Boolean)
                    .join(" · ")}
                  {assignment.uhid ? ` · UHID ${assignment.uhid}` : ""}
                </p>
              </div>
              <button
                type="button"
                aria-label={`Remove ${assignment.provider_name}`}
                onClick={() => void remove(assignment)}
                className="rounded-lg p-1.5 text-danger transition-colors hover:bg-danger/10"
              >
                <Trash2 className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      {assignments && assignments.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No providers assigned yet.
        </p>
      )}

      {(providers ?? []).length > 0 && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-40 flex-1 space-y-1.5 text-sm font-medium">
            Assign a provider
            <select
              value={providerId}
              onChange={(e) => setProviderId(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-2 py-1.5 text-sm"
            >
              <option value="">Choose…</option>
              {(providers ?? []).map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                  {provider.specialty ? ` (${provider.specialty})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="w-36 space-y-1.5 text-sm font-medium">
            UHID
            <input
              value={uhid}
              onChange={(e) => setUhid(e.target.value)}
              placeholder="Optional"
              className="w-full rounded-lg border border-input bg-background px-2 py-1.5 text-sm"
            />
          </label>
          <button
            type="button"
            onClick={() => void add()}
            disabled={busy || !providerId}
            className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <UserRoundPlus className="size-4" aria-hidden />
            )}
            Add
          </button>
        </div>
      )}
      {providers && providers.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Add doctors in{" "}
          <a href="/providers" className="text-primary hover:underline">
            Providers
          </a>{" "}
          first.
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  );
}
