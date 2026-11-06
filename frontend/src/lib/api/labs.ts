import { apiRequest } from "../api-client";
import type { Lab, LabCreate } from "../types/lab";

export function createLab(memberId: string, input: LabCreate): Promise<Lab> {
  return apiRequest<Lab>(`/members/${encodeURIComponent(memberId)}/labs`, {
    method: "POST",
    body: input,
  });
}
