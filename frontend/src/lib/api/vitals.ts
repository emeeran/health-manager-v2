import { apiRequest } from "../api-client";
import type { Vital, VitalCreate, VitalListParams } from "../types/vital";

export function listVitals(
  memberId: string,
  params: VitalListParams = {},
): Promise<Vital[]> {
  const search = new URLSearchParams();
  if (params.vital_type) search.set("vital_type", params.vital_type);
  if (params.since) search.set("since", params.since);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const query = search.toString();
  return apiRequest<Vital[]>(
    `/members/${encodeURIComponent(memberId)}/vitals${query ? `?${query}` : ""}`,
  );
}

export function createVital(
  memberId: string,
  input: VitalCreate,
): Promise<Vital> {
  return apiRequest<Vital>(`/members/${encodeURIComponent(memberId)}/vitals`, {
    method: "POST",
    body: input,
  });
}
