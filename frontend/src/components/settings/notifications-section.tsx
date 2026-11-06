import { Bell, BellRing, Loader2 } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { enablePush, notificationsSupported } from "../../lib/push";
import type { PushStatus } from "../../lib/types/push";

type Permission = NotificationPermission | "unsupported";

/** Current browser permission, or `unsupported` without the needed APIs. */
function currentPermission(): Permission {
  return notificationsSupported() ? Notification.permission : "unsupported";
}

/**
 * Browser notification (web push) enrolment.
 *
 * The browser side has two gates — notification permission and a push
 * subscription registered against the server's VAPID key — while the server
 * side only pushes when it has VAPID keys configured. Every browser-side
 * failure is a silent no-op: push is an enhancement, never a blocker.
 */
export function NotificationsSection() {
  const { data: status } = useSWR<PushStatus>("/notifications/push/status");
  const [permission, setPermission] = useState<Permission>(currentPermission);
  const [pushOn, setPushOn] = useState(false);
  const [working, setWorking] = useState(false);

  async function handleEnable() {
    if (!status?.enabled || !status.public_key) return;
    setWorking(true);
    try {
      const enabled = await enablePush(status.public_key);
      setPermission(currentPermission());
      setPushOn(enabled);
    } finally {
      setWorking(false);
    }
  }

  const granted = permission === "granted";

  return (
    <section
      aria-label="Notifications"
      className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Bell className="size-4 text-primary" aria-hidden />
        Notifications
      </h2>

      {!granted ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Get a browser notification for reminders and finished AI work, even
            when this tab is in the background.
          </p>
          <button
            type="button"
            onClick={() => void handleEnable()}
            disabled={working || permission === "unsupported"}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {working ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <BellRing className="size-4" aria-hidden />
            )}
            Enable browser notifications
          </button>
          {permission === "denied" && (
            <p className="text-xs text-muted-foreground">
              Notifications are blocked for this site — allow them in the
              browser's site settings to turn them back on.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-1 text-sm">
          <p className="flex items-center gap-2 font-medium">
            <BellRing className="size-4 text-primary" aria-hidden />
            Browser notifications are on.
          </p>
          <p className="text-muted-foreground">
            {status === undefined
              ? "Checking push delivery…"
              : status.enabled
                ? pushOn
                  ? "This browser is subscribed — reminders will show up here."
                  : "Push delivery is enabled on the server."
                : "Push delivery is not configured on the server."}
          </p>
        </div>
      )}
    </section>
  );
}
