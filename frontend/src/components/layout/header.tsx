import { LogOut, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import useSWR from "swr";
import { logout } from "../../lib/api/auth";
import { useEscClose } from "../../hooks/use-esc-close";
import { applyTheme, getInitialTheme, type Theme } from "../../lib/theme";
import type { User } from "../../lib/types/auth";
import { AiStatusIndicator } from "../ai-status-indicator";
import { NotificationBell } from "./notification-bell";
import { cn } from "../../lib/utils";

export function Header() {
  const navigate = useNavigate();
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const [menuOpen, setMenuOpen] = useState(false);
  useEscClose(menuOpen, () => setMenuOpen(false));
  const { data: user } = useSWR<User>("/auth/me");

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  async function handleLogout() {
    setMenuOpen(false);
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  function toggleTheme() {
    // Quick light/dark toggle; the full four-theme picker lives in
    // Settings → General. Sepia/grey resolve to light here.
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }

  return (
    <header className="flex h-16 items-center gap-3 border-b border-border bg-card px-4">
      <div className="ml-auto flex items-center gap-2">
        <AiStatusIndicator />
        <NotificationBell />
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {theme === "dark" ? (
            <Sun className="size-5" aria-hidden />
          ) : (
            <Moon className="size-5" aria-hidden />
          )}
        </button>

        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-muted"
          >
            <span
              className={cn(
                "flex size-7 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary",
              )}
            >
              {(user?.username ?? "?").charAt(0).toUpperCase()}
            </span>
            <span className="hidden font-medium sm:inline">
              {user?.username ?? "Account"}
            </span>
          </button>

          {menuOpen && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setMenuOpen(false)}
                aria-hidden
              />
              <div
                role="menu"
                className="absolute right-0 z-20 mt-1 w-44 rounded-lg border border-border bg-card py-1 shadow-lg"
              >
                <p className="px-3 py-1.5 text-xs text-muted-foreground">
                  {user ? `${user.username} · ${user.role}` : "Not signed in"}
                </p>
                <button
                  type="button"
                  role="menuitem"
                  onClick={handleLogout}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-danger transition-colors hover:bg-danger/10"
                >
                  <LogOut className="size-4" aria-hidden />
                  Logout
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
