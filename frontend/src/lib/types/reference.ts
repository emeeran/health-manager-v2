export interface BloodPressureBand {
  label: string;
  max_systolic: number;
  max_diastolic: number;
  color_key: string;
  citation: string;
}

export interface GlucoseReferenceRange {
  normal_low: number;
  normal_high: number;
  unit: string;
}

export interface ReferenceRanges {
  blood_pressure: { bands: BloodPressureBand[] };
  blood_glucose: {
    fasting: GlucoseReferenceRange;
    post_prandial: GlucoseReferenceRange;
  };
}

/**
 * Chart fill for a band color_key, with a stable fallback palette so unknown
 * keys still render in a distinguishable, severity-ordered color.
 */
const BAND_FALLBACKS = ["#16a34a", "#d97706", "#dc2626", "#991b1b"];

export function bandColor(colorKey: string, index: number): string {
  const known: Record<string, string> = {
    normal: "#16a34a",
    elevated: "#d97706",
    high: "#dc2626",
    crisis: "#991b1b",
  };
  return known[colorKey] ?? BAND_FALLBACKS[index % BAND_FALLBACKS.length];
}
