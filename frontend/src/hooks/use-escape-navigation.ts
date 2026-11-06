import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { closeTopOverlay } from "../lib/esc-stack";

/**
 * App-wide Escape key handling: close the topmost open overlay (dialog,
 * menu, popover); when none is open, go back one page — but only when there
 * is in-app history, so Esc never exits the app or bounces off the login.
 */
export function useEscapeNavigation() {
  const navigate = useNavigate();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.repeat) return;
      if (closeTopOverlay()) {
        event.preventDefault();
        return;
      }
      const index = (window.history.state as { idx?: number } | null)?.idx ?? 0;
      if (index > 0) {
        event.preventDefault();
        navigate(-1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);
}
