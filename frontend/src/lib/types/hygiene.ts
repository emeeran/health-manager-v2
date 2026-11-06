/** Duplicate record scan + merge (Phase 10 data hygiene). */

export interface DuplicatePair {
  /** Recommended keeper record. */
  primary_id: string;
  /** Record recommended to merge away. */
  duplicate_id: string;
  /** Comma-separated match reasons, e.g. "identical_content". */
  reason: string;
  /** Match strength, 1–3. */
  score: number;
}

export interface DedupResponse {
  pairs: DuplicatePair[];
  total_records_scanned: number;
}

/**
 * Merge direction for a pair when the user keeps `keeperId`:
 * the other record is POSTed as `{recordId}/merge` with `duplicate_of_id`
 * pointing at the keeper. Returns null for an invalid keeper id.
 */
export function mergeDirection(
  pair: DuplicatePair,
  keeperId: string,
): { duplicateId: string; primaryId: string } | null {
  if (keeperId === pair.primary_id) {
    return { duplicateId: pair.duplicate_id, primaryId: pair.primary_id };
  }
  if (keeperId === pair.duplicate_id) {
    return { duplicateId: pair.primary_id, primaryId: pair.duplicate_id };
  }
  return null;
}

/** Human label for a backend match reason token. */
export function reasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    identical_content: "Identical content",
    same_attachment: "Same attachment",
    same_type_adjacent_date: "Same type, adjacent date",
    similar_content: "Similar content",
  };
  return reason
    .split(",")
    .map((token) => labels[token.trim()] ?? token.trim())
    .join(" · ");
}
