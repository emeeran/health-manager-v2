import { apiRequest } from "../api-client";
import type { Vaccination, VaccinationCreateInput } from "../types/vaccination";

export function listVaccinations(memberId: string): Promise<Vaccination[]> {
  return apiRequest<Vaccination[]>(
    `/members/${encodeURIComponent(memberId)}/vaccinations`,
  );
}

export function createVaccination(
  memberId: string,
  input: VaccinationCreateInput,
): Promise<Vaccination> {
  return apiRequest<Vaccination>(
    `/members/${encodeURIComponent(memberId)}/vaccinations`,
    { method: "POST", body: input },
  );
}

export function deleteVaccination(
  memberId: string,
  vaccinationId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/vaccinations/${encodeURIComponent(vaccinationId)}`,
    { method: "DELETE" },
  );
}
