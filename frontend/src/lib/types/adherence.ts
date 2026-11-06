import { MEDICATION_SLOTS, type MedicationSlot } from "./medication";

export interface ScheduledDose {
  medication_id: string;
  medicine: string;
  dosage: string | null;
  /** One of `morning | breakfast | noon | evening | dinner | bedtime`. */
  slot: string;
  dose_count: number;
  /** ISO datetime of the dose, e.g. `2026-11-04T08:30:00`. */
  scheduled_time: string;
  annotation: string | null;
}

export interface PrnMedication {
  medication_id: string;
  medicine: string;
  dosage: string | null;
}

export interface AdherenceToday {
  /** ISO date, `YYYY-MM-DD`. */
  date: string;
  doses: ScheduledDose[];
  prn: PrnMedication[];
}

export const SLOT_ORDER: MedicationSlot[] = [...MEDICATION_SLOTS];

/**
 * Extract `HH:MM` from a dose's scheduled_time. The backend serializes it as
 * a full ISO datetime (`2026-11-04T08:30:00`); slicing the head of the string
 * would show the date instead of the clock time.
 */
export function doseTime(value: string): string {
  const tIndex = value.indexOf("T");
  return (tIndex === -1 ? value : value.slice(tIndex + 1)).slice(0, 5);
}
