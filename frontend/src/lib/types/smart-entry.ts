/** Smart entry: natural-language text → parsed draft → confirm persists. */

export interface SmartEntryFieldPreview {
  label: string;
  value: string;
}

export interface SmartEntryMemberMatch {
  id: string;
  name: string;
  /** "name" | "relationship" | "default". */
  matched_by: string;
}

export interface SmartEntryMedDraft {
  medicine: string;
  dosage?: string | null;
  timing?: string | null;
}

export interface SmartEntryLabDraft {
  test_name: string;
  result?: string | null;
  units?: string | null;
  value_num?: number | null;
  ref_low_num?: number | null;
  ref_high_num?: number | null;
  flag?: string | null;
}

export interface SmartEntryVitalDraft {
  vital_type: string;
  value_num: number;
  value_secondary?: number | null;
  unit?: string | null;
}

export interface SmartEntryDraft {
  member?: SmartEntryMemberMatch | null;
  record_type?: string | null;
  record_date?: string | null;
  diagnosis?: string | null;
  summary?: string | null;
  provider_name?: string | null;
  medications: SmartEntryMedDraft[];
  labs: SmartEntryLabDraft[];
  vitals: SmartEntryVitalDraft[];
  confidence?: "high" | "medium" | "low";
  preview_fields?: SmartEntryFieldPreview[];
}

export interface SmartEntryConfirmInput {
  member_id: string;
  record_type?: string | null;
  record_date?: string | null;
  diagnosis?: string | null;
  summary?: string | null;
  provider_name?: string | null;
  medications?: SmartEntryMedDraft[];
  labs?: SmartEntryLabDraft[];
  vitals?: SmartEntryVitalDraft[];
}

export interface SmartEntryConfirmResult {
  record_id: string | null;
  medication_ids: string[];
  lab_ids: string[];
  vital_ids: string[];
}

export const CONFIDENCE_STYLES: Record<string, string> = {
  high: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  medium: "bg-primary/10 text-primary",
  low: "bg-warning/15 text-warning-foreground",
};
