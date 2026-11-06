import { Loader2, ShieldCheck } from "lucide-react";
import useSWR from "swr";
import { getVerification } from "../../lib/api/ai";
import type { VerificationStatus } from "../../lib/types/ai";
import { cn } from "../../lib/utils";

const POLL_MS = 3_000;

const LABELS: Record<VerificationStatus, string> = {
  pending: "Verifying…",
  passed: "AI-verified",
  flagged: "AI flagged",
  failed: "AI check failed",
};

const CLASSES: Record<VerificationStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  passed: "bg-primary/10 text-primary",
  flagged: "bg-warning/15 text-warning-foreground",
  failed: "bg-danger/10 text-danger",
};

/**
 * Verification state of a generated artifact, polled until it settles.
 * Shows the verifier model name once the backend reports one, so users can
 * see a second model — not the author — signed off on the content.
 */
export function VerificationBadge({
  verificationId,
  initialStatus = "pending",
}: {
  verificationId: string;
  initialStatus?: VerificationStatus;
}) {
  const { data } = useSWR(
    initialStatus === "pending" ? `/verifications/${verificationId}` : null,
    () => getVerification(verificationId),
    {
      refreshInterval: (latest) =>
        (latest?.status ?? "pending") === "pending" ? POLL_MS : 0,
    },
  );
  const status: VerificationStatus = data?.status ?? initialStatus;
  const verifier = data?.verifier_name;

  return (
    <span
      title={data?.notes ?? undefined}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        CLASSES[status],
      )}
    >
      {status === "pending" ? (
        <Loader2 className="size-3 animate-spin" aria-hidden />
      ) : (
        <ShieldCheck className="size-3" aria-hidden />
      )}
      {LABELS[status]}
      {verifier && <span className="font-normal opacity-80">· {verifier}</span>}
    </span>
  );
}
