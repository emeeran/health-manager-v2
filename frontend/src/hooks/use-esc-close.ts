import { useEffect, useRef } from "react";
import { pushEscClose } from "../lib/esc-stack";

/**
 * Register an overlay's close callback on the global Escape stack while
 * `open` is true, so Esc closes the topmost overlay (see `esc-stack`).
 * The callback is kept in a ref, so passing an inline closure is fine.
 */
export function useEscClose(open: boolean, onClose: () => void) {
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    return pushEscClose(() => onCloseRef.current());
  }, [open]);
}
