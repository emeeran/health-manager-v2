import { apiRequest } from "../api-client";
import type { Reminder, ReminderCreate } from "../types/reminder";

export function listReminders(): Promise<Reminder[]> {
  return apiRequest<Reminder[]>("/reminders");
}

export function createReminder(input: ReminderCreate): Promise<Reminder> {
  return apiRequest<Reminder>("/reminders", { method: "POST", body: input });
}

export function setReminderDone(id: string, done: boolean): Promise<Reminder> {
  return apiRequest<Reminder>(`/reminders/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: { done },
  });
}

export function deleteReminder(id: string): Promise<void> {
  return apiRequest<void>(`/reminders/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
