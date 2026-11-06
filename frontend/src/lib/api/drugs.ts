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

/** Authenticated drug information for one medicine (openFDA → RxNorm → AI). */
export interface DrugInfo {
  brand: string | null;
  generic: string | null;
  manufacturer: string | null;
  ingredients: string | null;
  source: "openfda" | "rxnorm" | "ai" | "unavailable";
}

export function getDrugInfo(memberId: string, medicine: string): Promise<DrugInfo> {
  return apiRequest<DrugInfo>(
    `/members/${encodeURIComponent(memberId)}/drug-info?medicine=${encodeURIComponent(medicine)}`,
  );
}

/** One row of the deterministic price-comparison table. */
export interface PriceCompareItem {
  medicine: string;
  match: "exact" | "partial" | null;
  catalog_name: string | null;
  manufacturer: string | null;
  ingredients: string | null;
  package: string | null;
  price: number | null;
  product_id: string | null;
}

export interface PriceCompareResponse {
  items: PriceCompareItem[];
  matched_count: number;
  total_price: number | null;
  narrative: string | null;
  provider_used: string | null;
}

export function compareDrugPrices(
  medicines: string[],
  options: { narrate?: boolean; memberId?: string } = {},
): Promise<PriceCompareResponse> {
  return apiRequest<PriceCompareResponse>("/drugs/price-compare", {
    method: "POST",
    body: {
      medicines,
      narrate: options.narrate ?? true,
      member_id: options.memberId,
    },
  });
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
