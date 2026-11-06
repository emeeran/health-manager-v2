import { apiRequest } from "../api-client";
import type {
  Medication,
  MedicationCreate,
  MedicationStatus,
  MedicationUpdate,
} from "../types/medication";

export interface MedicationListParams {
  status?: MedicationStatus;
}

export function listMedications(
  memberId: string,
  params: MedicationListParams = {},
): Promise<Medication[]> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  const query = search.toString();
  return apiRequest<Medication[]>(
    `/members/${encodeURIComponent(memberId)}/medications${query ? `?${query}` : ""}`,
  );
}

export function createMedication(
  memberId: string,
  input: MedicationCreate,
): Promise<Medication> {
  return apiRequest<Medication>(
    `/members/${encodeURIComponent(memberId)}/medications`,
    { method: "POST", body: input },
  );
}

export function updateMedication(
  memberId: string,
  medicationId: string,
  input: MedicationUpdate,
): Promise<Medication> {
  return apiRequest<Medication>(
    `/members/${encodeURIComponent(memberId)}/medications/${encodeURIComponent(medicationId)}`,
    { method: "PATCH", body: input },
  );
}

export function deleteMedication(
  memberId: string,
  medicationId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/medications/${encodeURIComponent(medicationId)}`,
    { method: "DELETE" },
  );
}
