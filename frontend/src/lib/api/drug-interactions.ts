import { apiRequest } from "../api-client";
import type {
  DrugInteraction,
  DrugInteractionResponse,
} from "../types/drug-interaction";

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

/** Response of the two-medicine check (no member med list involved). */
export interface PairInteractionResponse {
  interactions: DrugInteraction[];
  provider_used: string | null;
  medicines_checked: number;
}

/** Check any two user-named medicines for interactions. */
export function checkPairInteraction(
  memberId: string,
  medicineA: string,
  medicineB: string,
): Promise<PairInteractionResponse> {
  return apiRequest<PairInteractionResponse>(
    `/members/${encodeURIComponent(memberId)}/drug-interactions/pair`,
    {
      method: "POST",
      body: { medicine_a: medicineA, medicine_b: medicineB },
    },
  );
}
