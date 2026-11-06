/** GET /notifications/push/status — enabled only when VAPID keys are set. */
export interface PushStatus {
  enabled: boolean;
  public_key: string | null;
}

export interface PushSubscribeInput {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}
