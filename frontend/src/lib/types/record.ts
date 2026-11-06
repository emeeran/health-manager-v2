import type { Attachment } from "./attachment";

export type ConfidentialityLevel = "household" | "caregiver" | "private";

export const RECORD_TYPES = [
  "doctor_visit",
  "lab_report",
  "prescription",
  "discharge_summary",
  "imaging",
  "vaccination",
  "other",
] as const;

export type RecordType = (typeof RECORD_TYPES)[number];

export interface HealthRecord {
  id: string;
  member_id: string;
  record_type: RecordType;
  /** ISO date, `YYYY-MM-DD`. */
  record_date: string;
  /** ISO time, `HH:MM:SS`, or null. */
  record_time: string | null;
  clinical_data: Record<string, unknown> | null;
  diagnosis: string | null;
  investigations: string | null;
  prescription_text: string | null;
  summary: string | null;
  doctor_name: string | null;
  provider_id: string | null;
  provider_name: string | null;
  tags: string[];
  /** household | caregiver | private — role-ceiling enforced at read time. */
  confidentiality_level?: ConfidentialityLevel | null;
  is_deleted: boolean;
  created_at: string;
  attachments: Attachment[];
}

export interface RecordCreate {
  record_type: RecordType;
  /** ISO date, `YYYY-MM-DD`. */
  record_date: string;
  record_time?: string;
  clinical_data?: Record<string, unknown>;
  diagnosis?: string;
  investigations?: string;
  prescription_text?: string;
  summary?: string;
  doctor_name?: string;
  provider_id?: string;
  tags?: string[];
  confidentiality_level?: ConfidentialityLevel;
}

/** Fields the backend merges into an existing record on PATCH. */
export interface RecordUpdate {
  clinical_data?: Record<string, unknown>;
  diagnosis?: string;
  summary?: string;
}

export interface RecordListParams {
  record_type?: RecordType;
  limit?: number;
  offset?: number;
}

export interface FilenameMatch {
  record_id: string;
  record_type: string;
  record_date: string;
  filename: string;
}
