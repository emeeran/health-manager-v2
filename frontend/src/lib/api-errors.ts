/**
 * Minimal global store for API error banners (5xx / network only, for now).
 * A real toast system replaces this in a later phase.
 */

let message: string | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function pushApiError(next: string): void {
  message = next;
  emit();
}

export function dismissApiError(): void {
  message = null;
  emit();
}

export function subscribeApiErrors(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getApiErrorSnapshot(): string | null {
  return message;
}
