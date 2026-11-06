import { Lock } from "lucide-react";
import type { ConfidentialityLevel } from "../../lib/types/record";

/**
 * Confidentiality levels — role ceilings enforced at read time:
 * household = everyone, caregiver = household + caregivers, private = admins.
 */
export const CONFIDENTIALITY_META: Record<
  ConfidentialityLevel,
  { label: string; badge: string; description: string }
> = {
  household: {
    label: "Household",
    badge: "bg-primary/10 text-primary",
    description: "Visible to everyone in the household",
  },
  caregiver: {
    label: "Caregiver",
    badge: "bg-warning/15 text-warning-foreground",
    description: "Visible to household members and caregivers",
  },
  private: {
    label: "Private",
    badge: "bg-danger/10 text-danger",
    description: "Visible to household admins only",
  },
};

export function ConfidentialityBadge({
  level,
}: {
  level?: ConfidentialityLevel | null;
}) {
  if (!level) return null;
  const meta = CONFIDENTIALITY_META[level] ?? CONFIDENTIALITY_META.household;
  return (
    <span
      title={meta.description}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium capitalize ${meta.badge}`}
    >
      <Lock className="size-3" aria-hidden />
      {meta.label}
    </span>
  );
}
