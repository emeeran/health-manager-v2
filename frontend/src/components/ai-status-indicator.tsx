import useSWR from "swr";
import type { AiStatus } from "../lib/types/ai";
import { cn } from "../lib/utils";

const REFRESH_MS = 5 * 60_000;

/**
 * Tiny availability dot for the header, driven by GET /ai/status every
 * 5 minutes. Hidden entirely while the request has not succeeded.
 */
export function AiStatusIndicator() {
  const { data } = useSWR<AiStatus>("/ai/status", {
    refreshInterval: REFRESH_MS,
  });
  if (!data || !Array.isArray(data.providers)) return null;

  const provider = data.default_provider;
  const label = provider ? `AI ready (${provider})` : "AI unavailable";
  const detail =
    data.providers.length > 0
      ? data.providers
          .map(
            (p) =>
              `${p.name}: ${p.available ? "available" : "unavailable"} · ${p.model}`,
          )
          .join("\n")
      : label;

  return (
    <span title={detail} className="flex items-center gap-1.5 text-xs">
      <span
        aria-hidden
        className={cn(
          "size-2 shrink-0 rounded-full",
          provider ? "bg-emerald-500" : "bg-muted-foreground/40",
        )}
      />
      <span className="hidden font-medium text-muted-foreground sm:inline">
        {label}
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
