import { apiRequest } from "../api-client";
import type {
  ConditionCreateInput,
  ConditionEpisode,
  ConditionStatus,
  ConditionUpdateInput,
} from "../types/condition";

export function listConditions(
  memberId: string,
  status?: ConditionStatus,
): Promise<ConditionEpisode[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<ConditionEpisode[]>(
    `/members/${encodeURIComponent(memberId)}/conditions${query}`,
  );
}

export function createCondition(
  memberId: string,
  input: ConditionCreateInput,
): Promise<ConditionEpisode> {
  return apiRequest<ConditionEpisode>(
    `/members/${encodeURIComponent(memberId)}/conditions`,
    { method: "POST", body: input },
  );
}

export function updateCondition(
  memberId: string,
  conditionId: string,
  input: ConditionUpdateInput,
): Promise<ConditionEpisode> {
  return apiRequest<ConditionEpisode>(
    `/members/${encodeURIComponent(memberId)}/conditions/${encodeURIComponent(conditionId)}`,
    { method: "PATCH", body: input },
  );
}

export function deleteCondition(
  memberId: string,
  conditionId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/conditions/${encodeURIComponent(conditionId)}`,
    { method: "DELETE" },
  );
}

/** Attach a record to an episode (idempotent re-link allowed). */
export function linkRecordToCondition(
  memberId: string,
  conditionId: string,
  recordId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/conditions/${encodeURIComponent(conditionId)}/records/${encodeURIComponent(recordId)}`,
    { method: "POST" },
  );
}

/** Attach a medication to an episode (idempotent re-link allowed). */
export function linkMedicationToCondition(
  memberId: string,
  conditionId: string,
  medicationId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/conditions/${encodeURIComponent(conditionId)}/medications/${encodeURIComponent(medicationId)}`,
    { method: "POST" },
  );
}
