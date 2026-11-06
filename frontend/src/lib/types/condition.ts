export type ConditionStatus = "active" | "chronic" | "resolved";

export interface ConditionEpisode {
  id: string;
  member_id: string;
  name: string;
  icd10_code: string | null;
  status: ConditionStatus;
  /** ISO date, `YYYY-MM-DD`, or null. */
  onset_date: string | null;
  resolution_date: string | null;
  notes: string | null;
  created_at: string;
  record_count: number;
  medication_count: number;
}

export interface ConditionCreateInput {
  name: string;
  icd10_code?: string | null;
  status?: ConditionStatus;
  onset_date?: string | null;
  resolution_date?: string | null;
  notes?: string | null;
}

export interface ConditionUpdateInput {
  name?: string;
  icd10_code?: string | null;
  status?: ConditionStatus;
  onset_date?: string | null;
  resolution_date?: string | null;
  notes?: string | null;
}

export const CONDITION_STATUSES: ConditionStatus[] = [
  "active",
  "chronic",
  "resolved",
];

export const CONDITION_STATUS_STYLES: Record<ConditionStatus, string> = {
  active: "bg-danger/10 text-danger",
  chronic: "bg-warning/15 text-warning-foreground",
  resolved: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
};

/**
 * Client-side mirror of the backend episode-course invariants so obvious
 * mistakes never leave the browser (the backend re-validates on every write).
 */
export function validateConditionCourse(
  input: ConditionCreateInput | ConditionUpdateInput,
): string | null {
  if (
    input.resolution_date &&
    input.onset_date &&
    input.resolution_date < input.onset_date
  ) {
    return "Resolution date cannot precede onset date.";
  }
  if (input.status === "resolved" && !input.resolution_date) {
    return "Resolved conditions require a resolution date.";
  }
  return null;
}
