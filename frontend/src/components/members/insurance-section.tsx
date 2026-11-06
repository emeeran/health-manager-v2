import { Loader2, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import {
  createClaim,
  createPolicy,
  deletePolicy,
  listClaims,
  listPolicies,
} from "../../lib/api/insurance";
import type { ClaimStatus } from "../../lib/types/insurance";
import { INPUT_CLASS } from "../../lib/utils";

/**
 * Member insurance: policies with claim tracking. Policy numbers are
 * decrypted server-side per viewer — the UI never handles raw ciphertext.
 */
export function InsuranceSection({ memberId }: { memberId: string }) {
  const {
    data: policies,
    isLoading,
    mutate,
  } = useSWR(memberId ? `members/${memberId}/insurance` : null, () =>
    listPolicies(memberId),
  );
  const [open, setOpen] = useState(false);

  async function remove(policyId: string) {
    if (!window.confirm("Delete this policy and its claims?")) return;
    await deletePolicy(memberId, policyId);
    await mutate();
  }

  return (
    <section
      aria-label="Insurance"
      className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <ShieldCheck className="size-4 text-primary" aria-hidden />
          Insurance
        </h2>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-muted"
        >
          <Plus className="size-3.5" aria-hidden />
          Policy
        </button>
      </div>

      {open && (
        <PolicyForm
          memberId={memberId}
          onDone={async () => {
            setOpen(false);
            await mutate();
          }}
        />
      )}

      {isLoading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" aria-hidden /> Loading…
        </p>
      )}

      {policies && policies.length === 0 && !open && (
        <p className="text-sm text-muted-foreground">No policies recorded.</p>
      )}

      <div className="space-y-3">
        {(policies ?? []).map((policy) => (
          <div
            key={policy.id}
            className="space-y-2 rounded-lg border border-border p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-medium">
                  {policy.insurer}
                  {policy.plan_name ? ` · ${policy.plan_name}` : ""}
                </p>
                <p className="font-mono text-xs text-muted-foreground">
                  {policy.policy_number}
                </p>
                <p className="text-xs text-muted-foreground">
                  {policy.sum_insured != null &&
                    `Sum insured ${policy.sum_insured.toLocaleString()}`}
                  {policy.valid_till
                    ? ` · valid till ${policy.valid_till}`
                    : ""}
                </p>
              </div>
              <button
                type="button"
                aria-label={`Delete ${policy.insurer} policy`}
                onClick={() => void remove(policy.id)}
                className="rounded-lg p-1.5 text-danger transition-colors hover:bg-danger/10"
              >
                <Trash2 className="size-4" aria-hidden />
              </button>
            </div>
            <ClaimsArea memberId={memberId} policyId={policy.id} />
          </div>
        ))}
      </div>
    </section>
  );
}

function PolicyForm({
  memberId,
  onDone,
}: {
  memberId: string;
  onDone: () => Promise<void>;
}) {
  const [insurer, setInsurer] = useState("");
  const [planName, setPlanName] = useState("");
  const [policyNumber, setPolicyNumber] = useState("");
  const [sumInsured, setSumInsured] = useState("");
  const [validTill, setValidTill] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createPolicy(memberId, {
        insurer: insurer.trim(),
        policy_number: policyNumber.trim(),
        ...(planName ? { plan_name: planName } : {}),
        ...(sumInsured ? { sum_insured: Number(sumInsured) } : {}),
        ...(validTill ? { valid_till: validTill } : {}),
      });
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save policy.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-2"
    >
      <label className="space-y-1.5 text-sm font-medium">
        Insurer
        <input
          required
          value={insurer}
          onChange={(e) => setInsurer(e.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className="space-y-1.5 text-sm font-medium">
        Plan
        <input
          value={planName}
          onChange={(e) => setPlanName(e.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className="space-y-1.5 text-sm font-medium">
        Policy number
        <input
          required
          value={policyNumber}
          onChange={(e) => setPolicyNumber(e.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className="space-y-1.5 text-sm font-medium">
        Sum insured
        <input
          type="number"
          min="0"
          value={sumInsured}
          onChange={(e) => setSumInsured(e.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className="space-y-1.5 text-sm font-medium">
        Valid till
        <input
          type="date"
          value={validTill}
          onChange={(e) => setValidTill(e.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <div className="flex items-end">
        <button
          type="submit"
          disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
          Save policy
        </button>
      </div>
      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger sm:col-span-2"
        >
          {error}
        </p>
      )}
    </form>
  );
}

function ClaimsArea({
  memberId,
  policyId,
}: {
  memberId: string;
  policyId: string;
}) {
  const { data: claims, mutate } = useSWR(
    `members/${memberId}/insurance/${policyId}/claims`,
    () => listClaims(memberId, policyId),
  );
  const [amount, setAmount] = useState("");
  const [claimedOn, setClaimedOn] = useState("");
  const [busy, setBusy] = useState(false);

  async function addClaim() {
    if (!amount || !claimedOn) return;
    setBusy(true);
    try {
      await createClaim(memberId, policyId, {
        amount: Number(amount),
        claimed_on: claimedOn,
      });
      setAmount("");
      setClaimedOn("");
      await mutate();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 border-t border-border pt-2">
      {(claims ?? []).map((claim) => (
        <div key={claim.id} className="flex items-center gap-2 text-xs">
          <span className="font-mono">{claim.claimed_on}</span>
          <span className="flex-1">
            {claim.amount.toLocaleString()}
            {claim.description ? ` — ${claim.description}` : ""}
          </span>
          <span className="rounded-full bg-muted px-2 py-0.5 font-medium">
            {claim.status}
          </span>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <input
          type="number"
          min="0"
          placeholder="Amount"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          aria-label="Claim amount"
          className="w-28 rounded-lg border border-input bg-background px-2 py-1 text-xs"
        />
        <input
          type="date"
          value={claimedOn}
          onChange={(e) => setClaimedOn(e.target.value)}
          aria-label="Claim date"
          className="rounded-lg border border-input bg-background px-2 py-1 text-xs"
        />
        <button
          type="button"
          onClick={() => void addClaim()}
          disabled={busy || !amount || !claimedOn}
          className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
        >
          + Claim
        </button>
      </div>
    </div>
  );
}

export type { ClaimStatus };
