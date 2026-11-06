/**
 * Global Escape-close stack. Overlays (dialogs, menus, popovers) register a
 * close callback while open; the app-wide Escape handler (see
 * `EscapeNavigation`) closes only the topmost one, falling back to history
 * back-navigation when no overlay is open.
 */
type EscClose = () => void;

const stack: EscClose[] = [];

/** Register an overlay's close callback; returns its unregister function. */
export function pushEscClose(onClose: EscClose): () => void {
  stack.push(onClose);
  return () => {
    const index = stack.indexOf(onClose);
    if (index !== -1) stack.splice(index, 1);
  };
}

/**
 * Close the topmost overlay, if any. Returns true when one was closed.
 * Pops the entry before calling so an overlay that closes by other means
 * (backdrop click, its own button) can't be re-triggered by a later Esc.
 */
export function closeTopOverlay(): boolean {
  const top = stack.pop();
  if (!top) return false;
  top();
  return true;
}
