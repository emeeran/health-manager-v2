/** AI-generated member insights (reports): generated via SSE, read back latest. */

/** Report kinds the /ai-tools pages can generate. */
export const INSIGHT_KINDS = [
  "health_insights",
  "smart_report",
  "pre_consultation",
  "consultant_note",
  "consolidated_report",
  "medication_report",
] as const;

export type InsightKind = (typeof INSIGHT_KINDS)[number];

export interface Insight {
  id: string;
  kind: InsightKind;
  content: string;
  /** Kind-specific provenance; shape varies per kind. */
  sources: Record<string, unknown> | null;
  verification_id: string | null;
  provider_used: string | null;
  created_at: string;
}

/** Human labels per kind, used across the /ai-tools pages. */
export const INSIGHT_KIND_META: Record<
  InsightKind,
  { label: string; description: string }
> = {
  health_insights: {
    label: "Health insights",
    description:
      "Comprehensive report across history, family history, visits, medications and labs",
  },
  smart_report: {
    label: "Quick health summary",
    description:
      "Short assessment of active conditions, medications and flagged results",
  },
  pre_consultation: {
    label: "Pre-consultation notes",
    description: "Notes and checklists to prepare for an upcoming visit",
  },
  consultant_note: {
    label: "Consultant note",
    description: "Concise doctor-facing snapshot to share at an appointment",
  },
  consolidated_report: {
    label: "Consolidated report",
    description: "Every visit, diagnosis and treatment in one ledger",
  },
  medication_report: {
    label: "Medication report",
    description: "Full medication history with dose changes over time",
  },
};
