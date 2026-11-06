import { apiRequest } from "../api-client";
import type { DedupResponse } from "../types/hygiene";
import type { HealthRecord } from "../types/record";

/** Scan a member's records for candidate duplicate pairs. */
export function scanRecordDuplicates(memberId: string): Promise<DedupResponse> {
  return apiRequest<DedupResponse>(
    `/members/${encodeURIComponent(memberId)}/records/duplicates`,
  );
}

/**
 * Merge `duplicateId` into `primaryId`; the duplicate is soft-deleted
 * (`merged_into_id` points at the keeper). Idempotent on re-merge.
 */
export function mergeRecord(
  memberId: string,
  duplicateId: string,
  primaryId: string,
): Promise<HealthRecord> {
  return apiRequest<HealthRecord>(
    `/members/${encodeURIComponent(memberId)}/records/${encodeURIComponent(duplicateId)}/merge`,
    { method: "POST", body: { duplicate_of_id: primaryId } },
  );
}
