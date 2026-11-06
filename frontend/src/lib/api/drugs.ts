import { apiRequest } from "../api-client";

/** One drug-compendium search hit. */
export interface DrugSearchResult {
  name: string;
  /** Generic/class summary line, when the compendium has one. */
  summary?: string | null;
  /** Raw compendium row, shape varies by source. */
  [key: string]: unknown;
}

export function searchDrugs(query: string): Promise<DrugSearchResult[]> {
  return apiRequest<DrugSearchResult[]>(
    `/drugs/search?q=${encodeURIComponent(query)}`,
  );
}

/** One reference document attached to a member's records. */
export interface MemberResource {
  id: string;
  title?: string | null;
  filename?: string | null;
  record_id?: string | null;
  [key: string]: unknown;
}

export function listMemberResources(
  memberId: string,
): Promise<MemberResource[]> {
  return apiRequest<MemberResource[]>(
    `/members/${encodeURIComponent(memberId)}/resources`,
  );
}
