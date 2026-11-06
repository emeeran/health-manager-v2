import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import { useI18n } from "../../lib/i18n";

/**
 * Slim banner shown when the browser reports it is offline. Data requests
 * will fail (the service worker never caches /api), but the cached app shell
 * keeps the UI navigable — hence "showing cached data".
 */
export function OfflineBanner() {
  const { t } = useI18n();
  const [online, setOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    const goOffline = () => setOnline(false);
    const goOnline = () => setOnline(true);
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
    };
  }, []);

  if (online) return null;

  return (
    <div
      role="status"
      className="flex items-center gap-2 border-b border-border bg-warning/10 px-4 py-1.5 text-sm text-foreground"
    >
      <WifiOff className="size-4 shrink-0 text-warning" aria-hidden />
      {t.offline.banner}
    </div>
  );
}
