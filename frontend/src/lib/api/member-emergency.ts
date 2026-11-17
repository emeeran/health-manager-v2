import { apiRequest } from "../api-client";
import type { EmergencyCard } from "../types/emergency";

export function getEmergencyCard(memberId: string): Promise<EmergencyCard> {
  return apiRequest<EmergencyCard>(
    `/members/${encodeURIComponent(memberId)}/emergency`,
  );
}
