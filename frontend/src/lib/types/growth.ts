/** CDC-referenced growth percentiles (Wave 6.1 parity). */

export type GrowthMeasure =
  "weight" | "length" | "stature" | "head_circumference" | "bmi";

export interface GrowthLms {
  l: number;
  m: number;
  s: number;
}

export interface GrowthRow {
  measure: GrowthMeasure | string;
  /** ISO date the reading was taken. */
  measured_at: string;
  value: number;
  /** Child's age in months at the reading. */
  age_months: number;
  z: number;
  percentile: number;
  implausible: boolean;
  lms: GrowthLms;
}

export interface GrowthReport {
  age_months: number | null;
  as_of?: string;
  rows: GrowthRow[];
  note?: string;
}

export const GROWTH_MEASURE_LABELS: Record<string, string> = {
  weight: "Weight-for-age",
  length: "Length-for-age",
  stature: "Stature-for-age",
  head_circumference: "Head circumference-for-age",
  bmi: "BMI-for-age",
};

export const GROWTH_MEASURE_UNITS: Record<string, string> = {
  weight: "kg",
  length: "cm",
  stature: "cm",
  head_circumference: "cm",
  bmi: "kg/m²",
};

/** Display order for the latest-assessment chips. */
export const GROWTH_MEASURE_ORDER: GrowthMeasure[] = [
  "weight",
  "stature",
  "length",
  "head_circumference",
  "bmi",
];

export interface GrowthBand {
  /** Lower percentile of the band. */
  low: number;
  high: number;
  label: string;
  color: string;
}

/** CDC band shading: 3rd/15th/50th/85th/97th. */
export const GROWTH_BANDS: GrowthBand[] = [
  { low: 3, high: 15, label: "3rd–15th", color: "#fbbf24" },
  { low: 15, high: 50, label: "15th–50th", color: "#34d399" },
  { low: 50, high: 85, label: "50th–85th", color: "#34d399" },
  { low: 85, high: 97, label: "85th–97th", color: "#fbbf24" },
];

export function growthBand(percentile: number): { chip: string; text: string } {
  if (percentile < 3)
    return { chip: "bg-danger/10 text-danger", text: "below 3rd" };
  if (percentile < 15)
    return { chip: "bg-warning/15 text-warning-foreground", text: "3rd–14th" };
  if (percentile <= 85)
    return {
      chip: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
      text: "15th–85th",
    };
  if (percentile <= 97)
    return { chip: "bg-warning/15 text-warning-foreground", text: "86th–97th" };
  return { chip: "bg-danger/10 text-danger", text: "above 97th" };
}

/** Latest row per measure, in stable display order. */
export function latestGrowthRows(rows: GrowthRow[]): GrowthRow[] {
  const latest = new Map<string, GrowthRow>();
  for (const row of rows) {
    const existing = latest.get(row.measure);
    if (!existing || row.measured_at > existing.measured_at)
      latest.set(row.measure, row);
  }
  return GROWTH_MEASURE_ORDER.flatMap((measure) => {
    const row = latest.get(measure);
    return row ? [row] : [];
  });
}

/* ── Milestones (Wave 6.2 parity) ─────────────────────────────────── */

export interface MilestoneRow {
  key: string;
  label: string;
  age_months: number;
  expected: "achieved" | "upcoming";
  achieved: boolean;
  achieved_on: string | null;
}

export interface MilestonesResponse {
  age_months: number | null;
  rows: MilestoneRow[];
}

/* ── Immunization schedule ────────────────────────────────────────── */

export type ScheduleDoseStatus = "complete" | "overdue" | "due" | "upcoming";

export interface ScheduleDose {
  antigen: string;
  label: string;
  due_date: string;
  status: ScheduleDoseStatus;
  given_date: string | null;
}

export interface ImmunizationSchedule {
  doses: ScheduleDose[];
  summary: { total: number; complete: number; overdue: number };
  disclaimer: string;
}

export const DOSE_STATUS_STYLES: Record<ScheduleDoseStatus, string> = {
  complete: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  overdue: "bg-danger/10 text-danger",
  due: "bg-warning/15 text-warning-foreground",
  upcoming: "bg-muted text-muted-foreground",
};
