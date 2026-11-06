import type { MedicationCreate } from "./medication";

export interface Member {
  id: string;
  name: string;
  relationship: string;
  birth_date: string | null;
  sex: string | null;
  phone: string | null;
  address: string | null;
  medical_history: string | null;
  family_medical_history: string | null;
  current_medications: string | null;
  blood_group: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  notes: string | null;
  /** Explicit opt-in for the audit agent's external fact-checking. */
  web_factcheck_consent?: boolean;
  created_at: string;
}

export interface MemberCreate {
  name: string;
  relationship: string;
  birth_date?: string;
  sex?: string;
  /** Current medications seeded as active rows at creation. */
  medications?: MedicationCreate[];
}

/** All fields optional — sent as a PATCH body. */
export interface MemberUpdate {
  name?: string;
  relationship?: string;
  birth_date?: string | null;
  sex?: string | null;
  phone?: string | null;
  address?: string | null;
  medical_history?: string | null;
  family_medical_history?: string | null;
  current_medications?: string | null;
  blood_group?: string | null;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
  notes?: string | null;
  web_factcheck_consent?: boolean;
}

export const RELATIONSHIPS = [
  "self",
  "spouse",
  "child",
  "parent",
  "sibling",
  "other",
] as const;

export const SEXES = ["male", "female", "other"] as const;
