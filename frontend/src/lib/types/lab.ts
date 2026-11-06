export const LAB_FLAGS = ["low", "normal", "high"] as const;

export type LabFlag = (typeof LAB_FLAGS)[number];

export interface Lab {
  id: string;
  member_id: string;
  record_id: string | null;
  test_name: string;
  result: string | null;
  units: string | null;
  ref_value: string | null;
  note: string | null;
  value_num: number | null;
  ref_low_num: number | null;
  ref_high_num: number | null;
  flag: string | null;
  /** ISO date, `YYYY-MM-DD`. */
  record_date: string | null;
  created_at: string;
}

export interface LabCreate {
  test_name: string;
  result?: string;
  units?: string;
  ref_value?: string;
  value_num?: number;
  flag?: LabFlag;
  record_date?: string;
}

export interface LabListParams {
  limit?: number;
}

/**
 * Derive the flag from a numeric value against its numeric reference range.
 * Returns null when either side is missing so the server value wins.
 */
export function computeFlag(
  valueNum: number | null | undefined,
  refLow: number | null | undefined,
  refHigh: number | null | undefined,
): LabFlag | null {
  if (valueNum === null || valueNum === undefined) return null;
  if (refHigh !== null && refHigh !== undefined && valueNum > refHigh)
    return "high";
  if (refLow !== null && refLow !== undefined && valueNum < refLow)
    return "low";
  if (refLow !== undefined || refHigh !== undefined) return "normal";
  return null;
}

/**
 * Parse a free-text reference like "70 - 100", "4.0-11.0" or "<200" into
 * numeric bounds so client-side flags can be computed before POSTing.
 */
export function parseRefValue(
  refValue: string,
): { low: number | null; high: number | null } | null {
  const trimmed = refValue.trim();
  const below = /^<\s*(\d+(?:\.\d+)?)$/.exec(trimmed);
  if (below) return { low: null, high: Number(below[1]) };
  const above = /^>\s*(\d+(?:\.\d+)?)$/.exec(trimmed);
  if (above) return { low: Number(above[1]), high: null };
  const range = /^(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)$/.exec(trimmed);
  if (range) return { low: Number(range[1]), high: Number(range[2]) };
  return null;
}

/** Human reference text, preferring the numeric range over the raw string. */
export function labReferenceText(lab: Lab): string {
  if (lab.ref_low_num !== null || lab.ref_high_num !== null) {
    const low = lab.ref_low_num ?? "";
    const high = lab.ref_high_num ?? "";
    if (lab.ref_low_num !== null && lab.ref_high_num !== null)
      return `${low} – ${high}`;
    return `${lab.ref_low_num !== null ? `≥ ${low}` : `≤ ${high}`}`;
  }
  return lab.ref_value ?? "—";
}
