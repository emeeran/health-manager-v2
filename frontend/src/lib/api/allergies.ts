import { apiRequest } from "../api-client";
import type {
  Allergy,
  AllergyConflict,
  AllergyCreateInput,
  AllergyUpdateInput,
} from "../types/allergy";

export function listAllergies(memberId: string): Promise<Allergy[]> {
  return apiRequest<Allergy[]>(
    `/members/${encodeURIComponent(memberId)}/allergies`,
  );
}

export function createAllergy(
  memberId: string,
  input: AllergyCreateInput,
): Promise<Allergy> {
  return apiRequest<Allergy>(
    `/members/${encodeURIComponent(memberId)}/allergies`,
    { method: "POST", body: input },
  );
}

export function updateAllergy(
  memberId: string,
  allergyId: string,
  input: AllergyUpdateInput,
): Promise<Allergy> {
  return apiRequest<Allergy>(
    `/members/${encodeURIComponent(memberId)}/allergies/${encodeURIComponent(allergyId)}`,
    { method: "PATCH", body: input },
  );
}

export function deleteAllergy(
  memberId: string,
  allergyId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/allergies/${encodeURIComponent(allergyId)}`,
    { method: "DELETE" },
  );
}

/**
 * Active medications matching a known allergy (name/ingredient match).
 * Decision-support hints for clinician review, not certainties.
 */
export function getAllergyConflicts(
  memberId: string,
): Promise<AllergyConflict[]> {
  return apiRequest<AllergyConflict[]>(
    `/members/${encodeURIComponent(memberId)}/allergy-conflicts`,
  );
}
