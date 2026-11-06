export type AllergySeverity = "mild" | "moderate" | "severe";

export interface Allergy {
  id: string;
  member_id: string;
  substance: string;
  severity: AllergySeverity;
  reaction: string | null;
  verified: boolean;
  created_at: string;
}

export interface AllergyCreateInput {
  substance: string;
  severity: AllergySeverity;
  reaction?: string | null;
  verified?: boolean;
}

export interface AllergyUpdateInput {
  substance?: string;
  severity?: AllergySeverity;
  reaction?: string | null;
  verified?: boolean;
}

/** A potential allergen–medication conflict (decision-support hint). */
export interface AllergyConflict {
  allergy: string;
  severity: string;
  medication: string;
  /** "ingredient" | "medicine_name". */
  matched_on: string;
}

export const ALLERGY_SEVERITIES: AllergySeverity[] = [
  "mild",
  "moderate",
  "severe",
];
