export type SymptomSeverity = "mild" | "moderate" | "severe";

export interface SymptomEntry {
  id: string;
  member_id: string;
  symptom: string;
  severity: SymptomSeverity;
  /** ISO date, `YYYY-MM-DD`. */
  started_at: string;
  resolved_at: string | null;
  notes: string | null;
  created_at?: string;
}

export interface SymptomCreateInput {
  symptom: string;
  severity: SymptomSeverity;
  started_at: string;
  resolved_at?: string | null;
  notes?: string | null;
}

export interface CorrelationHit {
  name: string;
  count: number;
  of: number;
}

export interface SymptomCorrelations {
  symptom: string;
  occurrences: number;
  first_seen: string;
  last_seen: string;
  severity_counts: Record<string, number>;
  with_medications: CorrelationHit[];
  with_abnormal_labs: CorrelationHit[];
  co_occurring_symptoms: CorrelationHit[];
  disclaimer: string;
}

/** Quick-tap presets, mirroring the backend `PRESET_SYMPTOMS`. */
export const SYMPTOM_PRESETS = [
  "headache",
  "nausea",
  "dizziness",
  "fatigue",
  "abdominal_pain",
  "chest_pain",
  "shortness_of_breath",
  "joint_pain",
  "back_pain",
  "rash",
  "fever",
  "cough",
  "insomnia",
  "anxiety",
  "swelling",
  "numbness",
  "palpitations",
  "constipation",
  "diarrhea",
  "vomiting",
] as const;

export const SYMPTOM_SEVERITIES: SymptomSeverity[] = [
  "mild",
  "moderate",
  "severe",
];

/** Group symptom entries by normalized symptom name, largest group first. */
export function groupBySymptom(
  entries: SymptomEntry[],
): [string, SymptomEntry[]][] {
  const groups = new Map<string, SymptomEntry[]>();
  for (const entry of entries) {
    const key = entry.symptom.trim().toLowerCase();
    const list = groups.get(key) ?? [];
    list.push(entry);
    groups.set(key, list);
  }
  return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
}
