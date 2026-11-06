/** AI-generated member insights (reports): generated via SSE, read back latest. */

/** Report kinds the /ai-tools pages can generate. */
export const INSIGHT_KINDS = [
  "health_insights",
  "smart_report",
  "pre_consultation",
  "consultant_note",
  "consolidated_report",
  "medication_report",
  "visit_summary",
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
  visit_summary: {
    label: "Doctor visit summary",
    description: "Summary of one specific visit — diagnosis, treatment and follow-up",
  },
};

/** Structured A5 pre-consultation note payload (report_service.PreConsultationA5). */
export interface A5Note {
  date: string;
  member_name: string;
  chronic_conditions: string[];
  chief_complaints: string[];
  to_discuss: string[];
  current_medications: string[];
}

/** Pull the A5 payload out of a pre_consultation insight, when present. */
export function a5NoteFrom(insight: Insight | null): A5Note | null {
  const payload = insight?.sources?.a5_note;
  if (!payload || typeof payload !== "object") return null;
  const note = payload as Partial<A5Note>;
  if (typeof note.date !== "string" || typeof note.member_name !== "string") {
    return null;
  }
  const list = (value: unknown): string[] =>
    Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  return {
    date: note.date,
    member_name: note.member_name,
    chronic_conditions: list(note.chronic_conditions),
    chief_complaints: list(note.chief_complaints),
    to_discuss: list(note.to_discuss),
    current_medications: list(note.current_medications),
  };
}

/** Plain-text rendering of the note — WhatsApp export / print sheet source. */
export function a5NoteToText(note: A5Note): string {
  const lines = [`Date: ${note.date}`, `Member Name: ${note.member_name}`];
  if (note.chronic_conditions.length) {
    lines.push(`Chronic: ${note.chronic_conditions.join(", ")}`);
  }
  if (note.chief_complaints.length) {
    lines.push(`C/c: ${note.chief_complaints.join("; ")}`);
  }
  lines.push("", "To discuss with doctor");
  note.to_discuss.forEach((item, i) => lines.push(`${i + 1}. ${item}`));
  if (note.current_medications.length) {
    lines.push("", `Current medications: ${note.current_medications.join(", ")}`);
  }
  return lines.join("\n");
}
