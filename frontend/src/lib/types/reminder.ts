export const REMINDER_REPEATS = ["none", "daily", "weekly", "monthly"] as const;

export type ReminderRepeat = (typeof REMINDER_REPEATS)[number];

export const REMINDER_REPEAT_LABELS: Record<ReminderRepeat, string> = {
  none: "Once",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
};

export interface Reminder {
  id: string;
  member_id: string | null;
  title: string;
  remind_at: string;
  repeat: ReminderRepeat;
  done: boolean;
  created_at: string;
}

export interface ReminderCreate {
  title: string;
  member_id?: string;
  remind_at: string;
  repeat: ReminderRepeat;
}
