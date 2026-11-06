/**
 * Pure helpers to turn a growth report into chart series.
 *
 * The CDC percentile *bands* are derived from each row's LMS reference values
 * (L, M, S at that age) using the standard LMS formula
 * `X(p) = M · (1 + L·S·z)^{1/L}`, linearly interpolated between assessment
 * ages. That gives approximate band curves from the data the API already
 * returns — no full CDC table is shipped to the client.
 */

import type { GrowthReport, GrowthRow } from "./types/growth";

/** Standard normal quantile (z) for the band percentiles (two-sided). */
export const PERCENTILE_Z: Record<number, number> = {
  3: -1.8808,
  15: -1.0364,
  50: 0,
  85: 1.0364,
  97: 1.8808,
};

/** LMS value-at-percentile: `M · (1 + L·S·z)^{1/L}`, M when L is 0. */
export function lmsValueAt(l: number, m: number, s: number, z: number): number {
  if (l === 0) return m * Math.exp(s * z);
  return m * Math.pow(1 + l * s * z, 1 / l);
}

function sortByAge(rows: GrowthRow[]): GrowthRow[] {
  return [...rows].sort((a, b) => a.age_months - b.age_months);
}

/** Interpolate a numeric field across rows ordered by age. */
function interpolate(
  rows: GrowthRow[],
  field: "l" | "m" | "s",
  age: number,
): number {
  const values = rows.map((row) => row.lms[field]);
  if (age <= rows[0].age_months) return values[0];
  if (age >= rows[rows.length - 1].age_months) return values[values.length - 1];
  for (let i = 1; i < rows.length; i++) {
    const ageA = rows[i - 1].age_months;
    const ageB = rows[i].age_months;
    if (age <= ageB) {
      const ratio = (age - ageA) / (ageB - ageA);
      return values[i - 1] + (values[i] - values[i - 1]) * ratio;
    }
  }
  return values[values.length - 1];
}

export interface GrowthChartSeries {
  /** One entry per assessment age: band boundaries + the actual reading. */
  points: {
    ageMonths: number;
    reading: number | null;
    p3: number;
    p15: number;
    p50: number;
    p85: number;
    p97: number;
  }[];
  readings: { ageMonths: number; value: number }[];
}

/**
 * Build band + reading series for one measure. Rows must share `measure`.
 * Band curves span the rows' age range; the actual readings ride along so
 * they render as a line over the shaded bands.
 */
export function buildGrowthSeries(rows: GrowthRow[]): GrowthChartSeries | null {
  const sorted = sortByAge(rows);
  if (sorted.length === 0) return null;

  const ages = sorted.map((row) => row.age_months);

  // Sample the interpolated bands at every assessment age plus the reading
  // ages, so the shaded region tracks the readings closely.
  const sampleAges = [...new Set([...ages])].sort((a, b) => a - b);

  const points = sampleAges.map((age) => {
    const l = interpolate(sorted, "l", age);
    const m = interpolate(sorted, "m", age);
    const s = interpolate(sorted, "s", age);
    const reading = sorted.find((row) => row.age_months === age);
    return {
      ageMonths: age,
      reading: reading ? reading.value : null,
      p3: lmsValueAt(l, m, s, PERCENTILE_Z[3]),
      p15: lmsValueAt(l, m, s, PERCENTILE_Z[15]),
      p50: lmsValueAt(l, m, s, PERCENTILE_Z[50]),
      p85: lmsValueAt(l, m, s, PERCENTILE_Z[85]),
      p97: lmsValueAt(l, m, s, PERCENTILE_Z[97]),
    };
  });

  return {
    points,
    readings: sorted.map((row) => ({
      ageMonths: row.age_months,
      value: row.value,
    })),
  };
}

/** Parse a report down to the rows for one measure. */
export function rowsForMeasure(
  report: GrowthReport,
  measure: string,
): GrowthRow[] {
  return report.rows.filter((row) => row.measure === measure);
}
