import { apiRequest } from "../api-client";
import type { NotificationList } from "../types/notification";

export function listNotifications(): Promise<NotificationList> {
  return apiRequest<NotificationList>("/notifications");
}

export function markAllRead(): Promise<{ marked: number }> {
  return apiRequest<{ marked: number }>("/notifications/read-all", {
    method: "POST",
  });
}

export function markRead(id: string): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(
    `/notifications/${encodeURIComponent(id)}/read`,
    { method: "POST" },
  );
}
