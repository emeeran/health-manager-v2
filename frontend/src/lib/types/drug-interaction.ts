/** Drug-interaction check over a member's active medications. */

export interface DrugInteraction {
  drugs: string[];
  severity: "high" | "moderate" | "low";
  description: string;
  recommendation: string;
  /** "drugbank" (authoritative) or "ai" (model estimate) when reported. */
  source?: string;
  /** Evidence level (e.g. DrugBank level_1/2) for authoritative hits. */
  evidence_level?: string;
}

export interface DrugInteractionResponse {
  interactions: DrugInteraction[];
  medications_checked: number;
  cached_at: string | null;
}

/** Severity → badge classes, shared by the interaction cards. */
export const SEVERITY_STYLES: Record<DrugInteraction["severity"], string> = {
  high: "bg-danger/10 text-danger border-danger/40",
  moderate: "bg-warning/15 text-warning-foreground border-warning/40",
  low: "bg-primary/10 text-primary border-primary/40",
};
