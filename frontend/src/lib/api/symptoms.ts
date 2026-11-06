import { apiRequest } from "../api-client";
import type {
  SymptomCorrelations,
  SymptomCreateInput,
  SymptomEntry,
} from "../types/symptom";

export function listSymptoms(memberId: string): Promise<SymptomEntry[]> {
  return apiRequest<SymptomEntry[]>(
    `/members/${encodeURIComponent(memberId)}/symptoms`,
  );
}

export function createSymptom(
  memberId: string,
  input: SymptomCreateInput,
): Promise<SymptomEntry> {
  return apiRequest<SymptomEntry>(
    `/members/${encodeURIComponent(memberId)}/symptoms`,
    { method: "POST", body: input },
  );
}

export function updateSymptom(
  memberId: string,
  entryId: string,
  input: Partial<SymptomCreateInput>,
): Promise<SymptomEntry> {
  return apiRequest<SymptomEntry>(
    `/members/${encodeURIComponent(memberId)}/symptoms/${encodeURIComponent(entryId)}`,
    { method: "PATCH", body: input },
  );
}

export function deleteSymptom(
  memberId: string,
  entryId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/symptoms/${encodeURIComponent(entryId)}`,
    { method: "DELETE" },
  );
}

/**
 * Co-occurrence analysis around a symptom's onsets. Correlations are counts,
 * never causes — the disclaimer ships with the data and must stay on screen.
 */
export function getSymptomCorrelations(
  memberId: string,
  symptom: string,
): Promise<SymptomCorrelations> {
  return apiRequest<SymptomCorrelations>(
    `/members/${encodeURIComponent(memberId)}/symptoms/correlations?symptom=${encodeURIComponent(symptom)}`,
  );
}
