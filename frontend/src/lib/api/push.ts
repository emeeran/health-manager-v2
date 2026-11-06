import { apiRequest } from "../api-client";
import type { PushSubscribeInput } from "../types/push";

export function subscribePush(input: PushSubscribeInput): Promise<void> {
  return apiRequest<void>("/notifications/push/subscribe", {
    method: "POST",
    body: input,
  });
}
