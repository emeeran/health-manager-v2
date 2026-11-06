export const MEDICATION_STATUSES = ["active", "completed", "stopped"] as const;

export type MedicationStatus = (typeof MEDICATION_STATUSES)[number];

/** Six daily slots — must stay in sync with the backend's
 * `dosing.SLOT_TIMES` (both key set and default times). */
export const MEDICATION_SLOTS = [
  "morning",
  "breakfast",
  "noon",
  "evening",
  "dinner",
  "bedtime",
] as const;

export type MedicationSlot = (typeof MEDICATION_SLOTS)[number];

export const SLOT_LABELS: Record<MedicationSlot, string> = {
  morning: "Morning",
  breakfast: "After Breakfast",
  noon: "Afternoon",
  evening: "Evening",
  dinner: "After Dinner",
  bedtime: "Bedtime",
};

/** Household default clock times per slot — mirrors `dosing.SLOT_TIMES`. */
export const DEFAULT_SLOT_TIMES: Record<MedicationSlot, string> = {
  morning: "08:30",
  breakfast: "09:30",
  noon: "13:00",
  evening: "18:00",
  dinner: "21:30",
  bedtime: "22:30",
};

export const SCHEDULE_TYPES = ["daily", "prn", "taper", "cycle"] as const;

export type ScheduleType = (typeof SCHEDULE_TYPES)[number];

export interface TaperParams {
  doses_start: number;
  step: number;
  step_every_days: number;
  floor: number;
}

export interface CycleParams {
  on_days: number;
  off_days: number;
}

/** Schedule params — the parsed `schedule_json` the API actually returns. */
export interface MedicationSchedule {
  slots?: MedicationSlot[];
  /** Per-slot clock overrides ("08:30") beating the household defaults. */
  slot_times?: Record<string, string>;
  taper?: TaperParams;
  cycle?: CycleParams;
}

export interface Medication {
  id: string;
  member_id: string;
  medicine: string;
  /** Presentation form: Tab | Cap | Inj | Syp | Cream | Drops | Inhaler | Other. */
  dose_form: string | null;
  dosage: string | null;
  timing: string | null;
  duration_days: number | null;
  start_date: string | null;
  schedule_type: ScheduleType;
  schedule_json: MedicationSchedule | null;
  provider_name: string | null;
  notes: string | null;
  status: MedicationStatus;
  created_at: string;
}

export interface MedicationCreate {
  medicine: string;
  /** Source record (e.g. the prescription this came from) for traceability. */
  record_id?: string;
  dose_form?: string;
  dosage?: string;
  timing?: string;
  duration_days?: number;
  start_date?: string;
  schedule_type: ScheduleType;
  slots?: MedicationSlot[];
  /** Per-slot clock overrides ("08:30"); keys ⊆ slots. */
  slot_times?: Record<string, string>;
  provider_name?: string;
  notes?: string;
  taper?: TaperParams;
  cycle?: CycleParams;
}

/** v1-carryover presentation forms for the medication table's Type column. */
export const DOSE_FORMS = [
  "Tab",
  "Cap",
  "Inj",
  "Syp",
  "Cream",
  "Drops",
  "Inhaler",
  "Other",
] as const;

export type DoseForm = (typeof DOSE_FORMS)[number];

export const DOSE_FORM_CLASSES: Record<DoseForm, string> = {
  Tab: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
  Cap: "bg-purple-500/15 text-purple-600 dark:text-purple-400",
  Inj: "bg-red-500/15 text-red-600 dark:text-red-400",
  Syp: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  Cream: "bg-pink-500/15 text-pink-600 dark:text-pink-400",
  Drops: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-400",
  Inhaler: "bg-teal-500/15 text-teal-600 dark:text-teal-400",
  Other: "bg-muted text-muted-foreground",
};

/** Badge class for a stored dose form, falling back to the muted style. */
export function doseFormClass(form: string | null): string {
  return (
    DOSE_FORM_CLASSES[(form ?? "Other") as DoseForm] ?? DOSE_FORM_CLASSES.Other
  );
}

/** PATCH body — widened for the schedule table's per-row Edit; slot edits
 * merge into schedule_json server-side (taper/cycle params are preserved). */
export interface MedicationUpdate {
  status?: MedicationStatus;
  medicine?: string;
  dose_form?: string | null;
  dosage?: string | null;
  timing?: string | null;
  duration_days?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  provider_name?: string | null;
  slots?: MedicationSlot[];
  slot_times?: Record<string, string>;
}

export const SCHEDULE_TYPE_LABELS: Record<ScheduleType, string> = {
  daily: "Daily",
  prn: "As needed (PRN)",
  taper: "Taper",
  cycle: "Cycle",
};

/** Slots covered by any of these medicines, in canonical morning→bedtime order. */
export function usedMedicationSlots(meds: Medication[]): MedicationSlot[] {
  const used = new Set<MedicationSlot>();
  for (const med of meds) {
    for (const slot of med.schedule_json?.slots ?? []) used.add(slot);
  }
  return MEDICATION_SLOTS.filter((slot) => used.has(slot));
}

/** The medicine's clock time for a slot — own override, else household default. */
export function medicationSlotTime(
  med: Medication,
  slot: MedicationSlot,
): string {
  return med.schedule_json?.slot_times?.[slot] ?? DEFAULT_SLOT_TIMES[slot];
}

/** Human duration for the schedule table: "30 days" or the ongoing default. */
export function medicationDurationLabel(med: Medication): string {
  return med.duration_days ? `${med.duration_days} days` : "Until next review";
}
