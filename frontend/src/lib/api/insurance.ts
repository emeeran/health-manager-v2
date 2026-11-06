import { apiRequest } from "../api-client";
import type {
  ClaimStatus,
  InsuranceClaim,
  InsurancePolicy,
} from "../types/insurance";

export function listPolicies(memberId: string): Promise<InsurancePolicy[]> {
  return apiRequest<InsurancePolicy[]>(
    `/members/${encodeURIComponent(memberId)}/insurance/policies`,
  );
}

export interface PolicyInput {
  insurer: string;
  plan_name?: string;
  policy_number: string;
  sum_insured?: number;
  valid_till?: string;
  notes?: string;
}

export function createPolicy(
  memberId: string,
  input: PolicyInput,
): Promise<InsurancePolicy> {
  return apiRequest<InsurancePolicy>(
    `/members/${encodeURIComponent(memberId)}/insurance/policies`,
    { method: "POST", body: input },
  );
}

export function deletePolicy(
  memberId: string,
  policyId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/insurance/policies/${encodeURIComponent(policyId)}`,
    { method: "DELETE" },
  );
}

export function listClaims(
  memberId: string,
  policyId: string,
): Promise<InsuranceClaim[]> {
  return apiRequest<InsuranceClaim[]>(
    `/members/${encodeURIComponent(memberId)}/insurance/policies/${encodeURIComponent(policyId)}/claims`,
  );
}

export function createClaim(
  memberId: string,
  policyId: string,
  input: {
    amount: number;
    claimed_on: string;
    status?: ClaimStatus;
    description?: string;
  },
): Promise<InsuranceClaim> {
  return apiRequest<InsuranceClaim>(
    `/members/${encodeURIComponent(memberId)}/insurance/policies/${encodeURIComponent(policyId)}/claims`,
    { method: "POST", body: input },
  );
}
