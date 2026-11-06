export const VITAL_TYPES = [
  "blood_pressure",
  "blood_glucose",
  "weight",
  "height",
  "temperature",
  "heart_rate",
  "spo2",
  "bmi",
  "hba1c",
] as const;

export type VitalType = (typeof VITAL_TYPES)[number];

export const GLUCOSE_CONTEXTS = ["fasting", "post_prandial", "random"] as const;

export type GlucoseContext = (typeof GLUCOSE_CONTEXTS)[number];

export interface Vital {
  id: string;
  member_id: string;
  record_id: string | null;
  vital_type: VitalType;
  value_num: number;
  value_secondary: number | null;
  unit: string | null;
  glucose_context: GlucoseContext | null;
  /** ISO datetime. */
  measured_at: string;
  source: string | null;
  created_at: string;
}

export interface VitalCreate {
  vital_type: VitalType;
  value_num: number;
  value_secondary?: number;
  unit?: string;
  glucose_context?: GlucoseContext;
  /** ISO datetime. */
  measured_at: string;
  source?: string;
}

export interface VitalListParams {
  vital_type?: VitalType;
  /** ISO datetime; only readings at or after this instant are returned. */
  since?: string;
  limit?: number;
}

export const VITAL_TYPE_META: Record<VitalType, { label: string }> = {
  blood_pressure: { label: "Blood pressure" },
  blood_glucose: { label: "Blood glucose" },
  weight: { label: "Weight" },
  height: { label: "Height" },
  temperature: { label: "Temperature" },
  heart_rate: { label: "Heart rate" },
  spo2: { label: "SpO2" },
  bmi: { label: "BMI" },
  hba1c: { label: "HbA1c" },
};

/** Canonical unit per vital type, auto-filled by the log form. */
export const VITAL_UNITS: Record<VitalType, string> = {
  blood_pressure: "mmHg",
  blood_glucose: "mg/dL",
  weight: "kg",
  height: "cm",
  temperature: "°C",
  heart_rate: "bpm",
  spo2: "%",
  bmi: "",
  hba1c: "%",
};

export const GLUCOSE_CONTEXT_LABELS: Record<GlucoseContext, string> = {
  fasting: "Fasting",
  post_prandial: "Post-meal",
  random: "Random",
};

/** Latest-first ordering as returned by the API (desc by measured_at). */
export function sortByMeasuredDesc(vitals: Vital[]): Vital[] {
  return [...vitals].sort(
    (a, b) =>
      new Date(b.measured_at).getTime() - new Date(a.measured_at).getTime(),
  );
}
