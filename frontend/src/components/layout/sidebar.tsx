import {
  ChevronLeft,
  Database,
  Home,
  MessageCircle,
  Pill,
  Settings,
  Sparkles,
  Stethoscope,
  Users,
} from "lucide-react";
import { useState } from "react";
import { NavLink } from "react-router-dom";
import { useI18n } from "../../lib/i18n";
import { cn } from "../../lib/utils";
import { AppLogo } from "./app-logo";

interface NavItem {
  to: string;
  labelKey: keyof ReturnType<typeof useI18n>["t"]["nav"];
  icon: typeof Home;
}

const items: NavItem[] = [
  { to: "/", labelKey: "home", icon: Home },
  { to: "/members", labelKey: "members", icon: Users },
  { to: "/providers", labelKey: "providers", icon: Stethoscope },
  { to: "/medicines", labelKey: "medicines", icon: Pill },
  { to: "/data-hygiene", labelKey: "dataHygiene", icon: Database },
  { to: "/chat", labelKey: "chat", icon: MessageCircle },
  { to: "/ai-tools", labelKey: "aiTools", icon: Sparkles },
  { to: "/settings", labelKey: "settings", icon: Settings },
];

const COLLAPSED_KEY = "sidebar-collapsed";

/** Below the md breakpoint there isn't room for 240px of labels, but hiding
 * the sidebar entirely would leave narrow (tiled / HiDPI-scaled) desktop
 * windows with no navigation — so they default to the icon rail. */
const NARROW_VIEWPORT_PX = 768;

/** Low-stakes UI state: localStorage alone is fine (no cookie mirror needed). */
function initialCollapsed(): boolean {
  try {
    const stored = localStorage.getItem(COLLAPSED_KEY);
    if (stored !== null) return stored === "1";
  } catch {
    // Storage unavailable (private mode) — fall through to the viewport.
  }
  return window.innerWidth < NARROW_VIEWPORT_PX;
}

export function Sidebar() {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(initialCollapsed);

  function toggle() {
    setCollapsed((value) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, value ? "0" : "1");
      } catch {
        // Storage unavailable (private mode) — collapse still works this session.
      }
      return !value;
    });
  }

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-border bg-card transition-[width] duration-200",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div
        className={cn(
          "flex h-16 shrink-0 items-center border-b border-border",
          collapsed ? "justify-between px-2" : "gap-2.5 px-5",
        )}
      >
        <AppLogo className="size-9 shrink-0" />
        {!collapsed && (
          <div className="min-w-0 leading-tight">
            <p className="truncate text-sm font-semibold">
              Family Health Manager
            </p>
            <p className="text-xs text-muted-foreground">v2</p>
          </div>
        )}
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="ml-auto flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ChevronLeft
            className={cn(
              "size-4 transition-transform",
              collapsed && "rotate-180",
            )}
            aria-hidden
          />
        </button>
      </div>

      <nav
        className={cn("flex flex-1 flex-col gap-1", collapsed ? "p-2" : "p-3")}
        aria-label="Main navigation"
      >
        {items.map(({ to, labelKey, icon: Icon }) => {
          const label = t.nav[labelKey];
          return (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              title={label}
              aria-label={collapsed ? label : undefined}
              className={({ isActive }) =>
                cn(
                  "flex items-center rounded-lg text-sm font-medium transition-colors",
                  collapsed ? "justify-center px-2 py-2" : "gap-3 px-3 py-2",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              {!collapsed && label}
            </NavLink>
          );
        })}
      </nav>

      {!collapsed && (
        <p className="border-t border-border px-5 py-3 text-xs text-muted-foreground">
          Self-hosted family health records
        </p>
      )}
    </aside>
  );
}
