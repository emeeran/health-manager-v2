import { apiRequest } from "../api-client";
import type {
  SmartEntryConfirmInput,
  SmartEntryConfirmResult,
  SmartEntryDraft,
} from "../types/smart-entry";

/**
 * Parse a natural-language health note into a structured draft.
 * The draft is only a preview — nothing is saved until confirmed.
 */
export function parseSmartEntry(text: string): Promise<SmartEntryDraft> {
  return apiRequest<SmartEntryDraft>("/smart-entry", {
    method: "POST",
    body: { text },
  });
}

/** Persist a parsed draft (record + medications/labs/vitals) for a member. */
export function confirmSmartEntry(
  input: SmartEntryConfirmInput,
): Promise<SmartEntryConfirmResult> {
  return apiRequest<SmartEntryConfirmResult>("/smart-entry/confirm", {
    method: "POST",
    body: input,
  });
}
