export interface InsurancePolicy {
  id: string;
  member_id: string;
  insurer: string;
  plan_name: string | null;
  policy_number: string;
  sum_insured: number | null;
  valid_till: string | null;
  notes: string | null;
  created_at: string;
}

export const CLAIM_STATUSES = [
  "submitted",
  "in_review",
  "approved",
  "rejected",
  "settled",
] as const;

export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

export interface InsuranceClaim {
  id: string;
  policy_id: string;
  amount: number;
  status: ClaimStatus;
  claimed_on: string;
  description: string | null;
  created_at: string;
}
