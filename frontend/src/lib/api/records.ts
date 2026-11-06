import { apiRequest } from "../api-client";
import type {
  FilenameMatch,
  HealthRecord,
  RecordCreate,
  RecordListParams,
} from "../types/record";

export function listRecords(
  memberId: string,
  params: RecordListParams = {},
): Promise<HealthRecord[]> {
  const search = new URLSearchParams();
  if (params.record_type) search.set("record_type", params.record_type);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const query = search.toString();
  return apiRequest<HealthRecord[]>(
    `/members/${encodeURIComponent(memberId)}/records${query ? `?${query}` : ""}`,
  );
}

export function createRecord(
  memberId: string,
  input: RecordCreate,
): Promise<HealthRecord> {
  return apiRequest<HealthRecord>(
    `/members/${encodeURIComponent(memberId)}/records`,
    { method: "POST", body: input },
  );
}

/** Body for applyExtraction — absent optional fields keep record values. */
export interface ApplyExtractionInput {
  clinical_data: Record<string, unknown>;
  summary?: string;
  diagnosis?: string;
  record_date?: string;
  doctor_name?: string;
}

export interface ApplyExtractionResult {
  record_id: string;
  labs_created: number;
  vitals_created: number;
}

/** Persist an AI extraction onto a record: clinical_data saved alongside it,
 * labs/vitals become linked rows. */
export function applyExtraction(
  memberId: string,
  recordId: string,
  input: ApplyExtractionInput,
): Promise<ApplyExtractionResult> {
  return apiRequest<ApplyExtractionResult>(
    `/members/${encodeURIComponent(memberId)}/records/${encodeURIComponent(recordId)}/apply-extraction`,
    { method: "POST", body: input },
  );
}

export function deleteRecord(
  memberId: string,
  recordId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/records/${encodeURIComponent(recordId)}`,
    { method: "DELETE" },
  );
}

/**
 * Look up existing records whose attachments share these filenames, so the UI
 * can warn before a likely-duplicate upload.
 */
export function checkFilenames(
  memberId: string,
  filenames: string[],
): Promise<{ matches: FilenameMatch[] }> {
  return apiRequest<{ matches: FilenameMatch[] }>(
    `/members/${encodeURIComponent(memberId)}/records/check-filenames`,
    { method: "POST", body: { filenames } },
  );
}
