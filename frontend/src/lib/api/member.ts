import { apiRequest } from "../api-client";
import type { EmergencyCard, HistoryItem } from "../types/emergency";

export function getEmergencyCard(memberId: string): Promise<EmergencyCard> {
  return apiRequest<EmergencyCard>(
    `/members/${encodeURIComponent(memberId)}/emergency`,
  );
}

export function getHistory(memberId: string): Promise<HistoryItem[]> {
  return apiRequest<HistoryItem[]>(
    `/members/${encodeURIComponent(memberId)}/history`,
  );
}
