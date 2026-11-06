import { subscribePush } from "./api/push";

/** Whether this browser exposes the Notification + Push plumbing at all. */
export function notificationsSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "Notification" in window &&
    "serviceWorker" in navigator &&
    "PushManager" in window
  );
}

/**
 * Convert a URL-safe base64 VAPID public key into the bytes
 * `pushManager.subscribe` expects for `applicationServerKey`.
 */
export function urlBase64ToUint8Array(
  base64String: string,
): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  return output;
}

/**
 * Ask for notification permission, then subscribe this browser to web push
 * through the service worker and register the subscription with the server.
 *
 * Any failure (no service worker, unsupported browser, denied permission,
 * network error) is a silent no-op that resolves to `false` — push is an
 * enhancement and must never block or break the settings page.
 */
export async function enablePush(publicKey: string): Promise<boolean> {
  if (!notificationsSupported()) return false;
  try {
    if (Notification.permission !== "granted") {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") return false;
    }
    const registration = await navigator.serviceWorker.ready;
    const existing = await registration.pushManager.getSubscription();
    const subscription =
      existing ??
      (await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      }));
    const json = subscription.toJSON();
    const { p256dh, auth } = json.keys ?? {};
    if (!json.endpoint || !p256dh || !auth) return false;
    await subscribePush({
      endpoint: json.endpoint,
      keys: { p256dh, auth },
    });
    return true;
  } catch {
    return false;
  }
}
