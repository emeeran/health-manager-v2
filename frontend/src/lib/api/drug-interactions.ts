import { apiRequest } from "../api-client";
import type { DrugInteractionResponse } from "../types/drug-interaction";

/** Check the member's active medications for interactions. */
export function checkDrugInteractions(
  memberId: string,
): Promise<DrugInteractionResponse> {
  return apiRequest<DrugInteractionResponse>(
    `/members/${encodeURIComponent(memberId)}/drug-interactions`,
    { method: "POST", body: {} },
  );
}

/** Last cached interaction result, when one exists. */
export function getLatestDrugInteractions(
  memberId: string,
): Promise<DrugInteractionResponse | null> {
  return apiRequest<DrugInteractionResponse | null>(
    `/members/${encodeURIComponent(memberId)}/latest-drug-interactions`,
  );
}
