/**
 * Pure state helpers for the single-page new-record form. Kept out of the
 * component so validation and payload assembly are unit-testable.
 */

import type { RecordCreate, RecordType } from "./types/record";
import { todayIso } from "./utils";

export interface WizardDraft {
  recordType: RecordType | null;
  recordDate: string;
  providerName: string;
  reason: string;
  investigations: string;
  diagnosis: string;
  note: string;
}

const LAST_DOCTOR_KEY = "health-manager:last-doctor-name";

/** Doctor name used on the previous record creation, if any. */
export function lastDoctorName(): string {
  try {
    return localStorage.getItem(LAST_DOCTOR_KEY) ?? "";
  } catch {
    return "";
  }
}

function rememberDoctorName(name: string) {
  try {
    if (name) localStorage.setItem(LAST_DOCTOR_KEY, name);
  } catch {
    // Storage unavailable (private mode) — prefill is best-effort.
  }
}

export function initialWizardDraft(): WizardDraft {
  return {
    recordType: null,
    recordDate: todayIso(),
    providerName: lastDoctorName(),
    reason: "",
    investigations: "",
    diagnosis: "",
    note: "",
  };
}

/** Form-level validation: only type and date are required. */
export function wizardFormError(draft: WizardDraft): string | null {
  if (!draft.recordType) return "Please select a record type.";
  if (!draft.recordDate) return "Record date is required.";
  return null;
}

export function canSubmit(draft: WizardDraft): boolean {
  return wizardFormError(draft) === null;
}

/** Provider name → the matching directory provider's id, if any. */
export function matchProviderId(
  providerName: string,
  providers: { id: string; name: string }[],
): string | undefined {
  const needle = providerName.trim().toLowerCase();
  if (!needle) return undefined;
  return providers.find((p) => p.name.toLowerCase() === needle)?.id;
}

/** Assemble the API payload from the draft; empty optional fields omitted.
 * The visit's "reason" leads the stored summary (it IS the summary for a
 * plain visit); the note, when also filled, follows it. */
export function buildRecordPayload(
  draft: WizardDraft,
  providers: { id: string; name: string }[] = [],
): RecordCreate {
  if (!draft.recordType) throw new Error("Record type is required.");
  if (!draft.recordDate) throw new Error("Record date is required.");
  const summary = [draft.reason.trim(), draft.note.trim()]
    .filter(Boolean)
    .join("\n");
  const providerName = draft.providerName.trim();
  if (providerName) rememberDoctorName(providerName);
  const providerId = matchProviderId(providerName, providers);
  return {
    record_type: draft.recordType,
    record_date: draft.recordDate,
    ...(draft.diagnosis ? { diagnosis: draft.diagnosis } : {}),
    ...(draft.investigations ? { investigations: draft.investigations } : {}),
    ...(summary ? { summary } : {}),
    ...(providerName ? { doctor_name: providerName } : {}),
    ...(providerId ? { provider_id: providerId } : {}),
  };
}
