export interface Vaccination {
  id: string;
  member_id: string;
  name: string;
  /** ISO date, `YYYY-MM-DD`. */
  date_administered: string;
  booster_due_date: string | null;
  notes: string | null;
  created_at: string;
}

export interface VaccinationCreateInput {
  name: string;
  date_administered: string;
  booster_due_date?: string | null;
  notes?: string | null;
}

export function isBoosterOverdue(boosterDueDate: string | null): boolean {
  if (!boosterDueDate) return false;
  const due = new Date(boosterDueDate);
  return !Number.isNaN(due.getTime()) && due.getTime() < Date.now();
}
