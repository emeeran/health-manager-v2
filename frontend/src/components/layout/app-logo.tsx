import { cn } from "../../lib/utils";

/**
 * Brand mark — the red stethoscope logo, served from /icons/icon.svg so the
 * favicon and the in-app logo stay one asset. Sits on a card-colored chip
 * because the artwork is red-on-transparent.
 */
export function AppLogo({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "flex items-center justify-center rounded-lg border border-border bg-card",
        className,
      )}
    >
      <img
        src="/icons/icon.svg"
        alt=""
        aria-hidden
        className="size-[72%] object-contain"
      />
    </span>
  );
}
