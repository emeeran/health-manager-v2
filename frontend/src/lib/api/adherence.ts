import { apiRequest } from "../api-client";
import type { AdherenceToday } from "../types/adherence";

export function getAdherenceToday(memberId: string): Promise<AdherenceToday> {
  return apiRequest<AdherenceToday>(
    `/members/${encodeURIComponent(memberId)}/adherence/today`,
  );
}
