export interface BloodPressureBand {
  label: string;
  /** Band ceiling; null for the open-ended hypertensive-crisis band. */
  max_systolic: number | null;
  max_diastolic: number | null;
  color_key: string;
  citation: string;
}

export interface GlucoseReferenceRange {
  normal_low: number;
  normal_high: number;
  unit: string;
}

export interface LabReferenceRange {
  test_name: string;
  normal_low: number;
  normal_high: number;
  unit: string;
}

export interface ReferenceRanges {
  blood_pressure: { bands: BloodPressureBand[] };
  blood_glucose: {
    fasting: GlucoseReferenceRange;
    post_prandial: GlucoseReferenceRange;
    random: GlucoseReferenceRange;
  };
  labs: Record<string, LabReferenceRange>;
}

/**
 * Chart fill for a band color_key, with a stable fallback palette so unknown
 * keys still render in a distinguishable, severity-ordered color.
 */
const BAND_FALLBACKS = ["#16a34a", "#d97706", "#dc2626", "#991b1b"];

export function bandColor(colorKey: string, index: number): string {
  // color_key values come from backend reference_ranges.py (ok/warning/danger).
  const known: Record<string, string> = {
    ok: "#16a34a",
    warning: "#d97706",
    danger: "#dc2626",
  };
  return known[colorKey] ?? BAND_FALLBACKS[index % BAND_FALLBACKS.length];
}
