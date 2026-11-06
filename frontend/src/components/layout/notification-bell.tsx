import { Bell } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import {
  listNotifications,
  markAllRead,
  markRead,
} from "../../lib/api/notifications";
import { useEscClose } from "../../hooks/use-esc-close";
import type { NotificationList } from "../../lib/types/notification";
import { cn } from "../../lib/utils";

/**
 * Header notification bell: unread badge polled every 60 s, dropdown with the
 * latest items, per-item and mark-all read.
 */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  useEscClose(open, () => setOpen(false));
  const { data, mutate } = useSWR<NotificationList>(
    "/notifications",
    listNotifications,
    {
      refreshInterval: 60_000,
    },
  );
  const unread = data?.unread ?? 0;

  async function handleMarkAll() {
    await markAllRead();
    await mutate();
  }

  async function handleMarkRead(id: string) {
    await markRead(id);
    await mutate();
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}
        aria-expanded={open}
        className="relative rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Bell className="size-5" aria-hidden />
        {unread > 0 && (
          <span
            data-testid="unread-badge"
            className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white"
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div
            role="menu"
            className="absolute right-0 z-20 mt-1 w-80 rounded-lg border border-border bg-card py-1 shadow-lg"
          >
            <div className="flex items-center justify-between px-3 py-1.5">
              <p className="text-xs text-muted-foreground">Notifications</p>
              {unread > 0 && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => void handleMarkAll()}
                  className="text-xs text-primary hover:underline"
                >
                  Mark all read
                </button>
              )}
            </div>
            {(data?.items ?? []).length === 0 ? (
              <p className="px-3 py-4 text-center text-sm text-muted-foreground">
                Nothing here yet.
              </p>
            ) : (
              <ul className="max-h-80 overflow-y-auto">
                {data?.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => void handleMarkRead(item.id)}
                      className={cn(
                        "flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-muted",
                        !item.read && "bg-primary/5",
                      )}
                    >
                      <span
                        className={cn("text-sm", !item.read && "font-semibold")}
                      >
                        {item.title}
                      </span>
                      {item.body && (
                        <span className="text-xs text-muted-foreground">
                          {item.body}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
