import {
  CircleAlert,
  CircleCheck,
  ExternalLink,
  Globe2,
  Loader2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { getVerification } from "../../lib/api/ai";
import type {
  AuditReport,
  ClaimAudit,
  ClaimVerdict,
  Verification,
} from "../../lib/types/ai";
import { cn } from "../../lib/utils";

const POLL_MS = 3_000;

const VERDICT_META: Record<
  ClaimVerdict,
  { label: string; className: string; icon: typeof CircleCheck }
> = {
  supported: {
    label: "Supported",
    className: "bg-primary/10 text-primary",
    icon: CircleCheck,
  },
  external_verified: {
    label: "Web-verified",
    className: "bg-primary/10 text-primary",
    icon: Globe2,
  },
  contradicted: {
    label: "Contradicted",
    className: "bg-danger/10 text-danger",
    icon: CircleAlert,
  },
  not_in_records: {
    label: "Not in records",
    className: "bg-warning/15 text-warning-foreground",
    icon: ShieldAlert,
  },
  unverified: {
    label: "Unverified",
    className: "bg-muted text-muted-foreground",
    icon: CircleAlert,
  },
};

const CATEGORY_LABELS: Record<ClaimAudit["category"], string> = {
  record_fact: "Record fact",
  condition: "Condition",
  prognosis: "Prognosis",
  guideline: "Guideline",
  drug_interaction: "Drug interaction",
  recommendation: "Recommendation",
};

function isVerified(claim: ClaimAudit): boolean {
  return claim.verdict === "supported" || claim.verdict === "external_verified";
}

/**
 * Claim-level audit table for a report, health answer or chat reply.
 *
 * Reads the same verification row the badge polls; collapsible, and open by
 * default when anything needs review. Evidence is the record rows the audit
 * cited; web links are external and never fetched by the app.
 */
export function AuditPanel({ verificationId }: { verificationId: string }) {
  const { data } = useSWR<Verification>(
    `/verifications/${verificationId}`,
    () => getVerification(verificationId),
    {
      refreshInterval: (latest) =>
        (latest?.status ?? "pending") === "pending" ? POLL_MS : 0,
    },
  );
  const [open, setOpen] = useState<boolean | null>(null);
  const audit = data?.audit ?? null;

  if (!audit) {
    if ((data?.status ?? "pending") === "pending") {
      return (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" aria-hidden />
          Auditing claims…
        </p>
      );
    }
    return null;
  }

  const expanded = open ?? audit.overall !== "passed";
  const verified = audit.claims.filter(isVerified).length;
  const review = audit.claims.filter(
    (claim) => claim.category !== "recommendation" && !isVerified(claim),
  ).length;

  return (
    <section
      data-testid="audit-panel"
      aria-label="Claim audit"
      className="rounded-xl border border-border bg-muted/30 p-3 text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium">
          {audit.overall === "passed" ? (
            <ShieldCheck className="size-4 text-primary" aria-hidden />
          ) : (
            <ShieldAlert className="size-4 text-warning-foreground" aria-hidden />
          )}
          {audit.overall === "passed" ? "Audit passed" : "Audit needs review"}
          <span className="font-normal text-muted-foreground">
            · {verified}/{audit.claims.length} verified
            {review > 0 && ` · ${review} to review`}
            {audit.web_used && " · web-checked"}
          </span>
        </p>
        <button
          type="button"
          onClick={() => setOpen(!expanded)}
          aria-expanded={expanded}
          className="text-xs font-medium text-primary hover:underline"
        >
          {expanded ? "Hide audit" : "View audit"}
        </button>
      </div>

      {audit.summary && (
        <p className="mt-1.5 text-xs text-muted-foreground">{audit.summary}</p>
      )}

      {expanded && (
        <div className="mt-3 space-y-3">
          <ClaimList audit={audit} />
          <GapList audit={audit} />
          <InteractionList audit={audit} />
          <WebSourceList audit={audit} />
          <p className="text-xs text-muted-foreground">
            An audit checks the narrative against this member's records and,
            when enabled, public references. It is not a medical opinion.
          </p>
        </div>
      )}
    </section>
  );
}

function ClaimList({ audit }: { audit: AuditReport }) {
  if (audit.claims.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No individual claims were extracted from this narrative.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {audit.claims.map((claim, index) => {
        const meta = VERDICT_META[claim.verdict];
        const Icon = meta.icon;
        return (
          <li
            key={`${index}-${claim.claim.slice(0, 24)}`}
            className="rounded-lg border border-border bg-card p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm">{claim.claim}</p>
              <span
                className={cn(
                  "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                  meta.className,
                )}
              >
                <Icon className="size-3" aria-hidden />
                {meta.label}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {CATEGORY_LABELS[claim.category]}
              {claim.severity !== "info" && ` · ${claim.severity}`}
            </p>
            {claim.evidence.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-xs">
                {claim.evidence.map((item) => (
                  <li key={item.ref} className="text-muted-foreground">
                    <span className="font-medium text-foreground">
                      {item.label}
                    </span>
                    {item.value && `: ${item.value}`}
                    {item.date && ` (${item.date})`}
                  </li>
                ))}
              </ul>
            )}
            {claim.note && (
              <p className="mt-1.5 text-xs text-muted-foreground">{claim.note}</p>
            )}
            {claim.web && claim.web.results.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-xs">
                {claim.web.results.map((source) => (
                  <li key={source.url}>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      {source.title}
                      <ExternalLink className="size-3" aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function GapList({ audit }: { audit: AuditReport }) {
  if (audit.gaps.length === 0) return null;
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Record gaps
      </h4>
      <ul className="space-y-1 text-xs text-muted-foreground">
        {audit.gaps.map((gap) => (
          <li key={`${gap.domain}-${gap.detail}`}>
            <span className="font-medium text-foreground">{gap.domain}</span>
            {gap.status === "stale" ? " (stale)" : " (missing)"} — {gap.detail}
          </li>
        ))}
      </ul>
    </div>
  );
}

function InteractionList({ audit }: { audit: AuditReport }) {
  if (audit.interactions.length === 0) return null;
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Drug interactions
      </h4>
      <ul className="space-y-1 text-xs">
        {audit.interactions.map((row, index) => {
          const drugs = Array.isArray(row.drugs) ? row.drugs.join(" + ") : "Interaction";
          const description =
            typeof row.description === "string" ? row.description : "";
          const severity =
            typeof row.severity === "string" ? row.severity : "moderate";
          return (
            <li key={`${index}-${drugs}`} className="text-muted-foreground">
              <span className="font-medium text-foreground">{drugs}</span>
              {` (${severity})`}
              {description && ` — ${description}`}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function WebSourceList({ audit }: { audit: AuditReport }) {
  if (!audit.web_used || audit.sources.length === 0) return null;
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Web sources
      </h4>
      <ul className="space-y-1 text-xs">
        {audit.sources.map((source) => (
          <li key={source.url}>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              {source.title}
              <ExternalLink className="size-3" aria-hidden />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
