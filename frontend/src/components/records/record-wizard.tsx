import { useRef, useState, type FormEvent } from "react";
import { Loader2, Paperclip } from "lucide-react";
import useSWR from "swr";
import { createRecord, listRecords } from "../../lib/api/records";
import { uploadAttachments } from "../../lib/api/attachments";
import { listProviders } from "../../lib/api/providers";
import { recordTypeMeta } from "../../lib/record-types";
import {
  buildRecordPayload,
  canSubmit,
  initialWizardDraft,
  wizardFormError,
  type WizardDraft,
} from "../../lib/wizard-state";
import { RECORD_TYPES, type HealthRecord } from "../../lib/types/record";
import { INPUT_CLASS } from "../../lib/utils";

/** Prescription integration hint: shows which doctor visit a prescription
 * will link to (±7 days) and what auto-fills from it, or that it stays
 * standalone. Purely informational — linking happens server-side. */
function VisitLinkHint({
  memberId,
  recordDate,
}: {
  memberId: string;
  recordDate: string;
}) {
  const { data: visits } = useSWR(
    recordDate ? ["records", memberId, "doctor_visit"] : null,
    () => listRecords(memberId, { record_type: "doctor_visit", limit: 50 }),
  );

  if (!recordDate || !visits?.length) return null;
  const date = new Date(`${recordDate}T00:00:00`);
  const nearby = visits
    .map((visit) => ({
      visit,
      days: Math.abs(
        (date.getTime() - new Date(`${visit.record_date}T00:00:00`).getTime()) /
          86_400_000,
      ),
    }))
    .filter(({ days }) => days <= 7)
    .sort((a, b) => a.days - b.days);

  if (nearby.length === 0) {
    return (
      <p className="sm:col-span-2 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
        No doctor visit within 7 days of this date — the prescription will be
        saved as standalone.
      </p>
    );
  }
  const linked = nearby[0].visit;
  return (
    <p className="sm:col-span-2 rounded-lg bg-primary/10 px-3 py-2 text-xs text-primary">
      Will link to the {linked.record_date} doctor visit
      {linked.doctor_name ? ` with ${linked.doctor_name}` : ""} — doctor and
      diagnosis auto-fill from it when left empty.
    </p>
  );
}

/**
 * Single-page new-record form (Type | Date / Doctor | Reason /
 * Investigations | Diagnosis / Note / Attachments). Replaced the former
 * three-step wizard; creation path on the member page.
 */
export default function RecordWizard({
  memberId,
  onCreated,
}: {
  memberId: string;
  /** Second arg = attached files count; >0 asks the caller to open the
   * record page in auto-extract mode. */
  onCreated: (record: HealthRecord, attachedFiles: number) => void;
}) {
  const [draft, setDraft] = useState<WizardDraft>(initialWizardDraft);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Provider directory feeds the Doctor/Provider autocomplete; the API
  // call is cheap and the list is small.
  const { data: providers = [] } = useSWR("providers", listProviders);

  function update<K extends keyof WizardDraft>(key: K, value: WizardDraft[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const error = wizardFormError(draft);
    if (error) {
      setFormError(error);
      return;
    }
    setFormError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const record = await createRecord(
        memberId,
        buildRecordPayload(draft, providers),
      );
      // Best-effort: prescriptions/lab reports attached at creation time. A
      // failure never loses the record — the detail page can re-upload.
      try {
        if (files.length > 0) {
          await uploadAttachments(memberId, record.id, files);
        }
      } catch {
        setSubmitError(
          "Record created, but the attachment upload failed — attach the files from the record page.",
        );
      }
      onCreated(record, files.length);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Could not create record.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border bg-card p-5 shadow-sm"
      aria-label="New record form"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {draft.recordType === "prescription" && (
          <VisitLinkHint memberId={memberId} recordDate={draft.recordDate} />
        )}
        <label className="space-y-1.5 text-sm font-medium">
          Type
          <select
            required
            value={draft.recordType ?? ""}
            onChange={(e) =>
              update(
                "recordType",
                (e.target.value || null) as WizardDraft["recordType"],
              )
            }
            className={INPUT_CLASS}
          >
            <option value="" disabled>
              Select type…
            </option>
            {RECORD_TYPES.map((type) => (
              <option key={type} value={type}>
                {recordTypeMeta(type).label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Date
          <input
            type="date"
            required
            value={draft.recordDate}
            onChange={(e) => update("recordDate", e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Doctor / Provider
          <input
            list="provider-options"
            placeholder="Optional"
            value={draft.providerName}
            onChange={(e) => update("providerName", e.target.value)}
            className={INPUT_CLASS}
          />
          <datalist id="provider-options">
            {providers.map((provider) => (
              <option key={provider.id} value={provider.name} />
            ))}
          </datalist>
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Reason
          <input
            placeholder="e.g. follow-up, fever, routine check-up"
            value={draft.reason}
            onChange={(e) => update("reason", e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Investigations
          <input
            placeholder="e.g. CBC, X-ray chest"
            value={draft.investigations}
            onChange={(e) => update("investigations", e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Diagnosis
          <input
            placeholder="Optional"
            value={draft.diagnosis}
            onChange={(e) => update("diagnosis", e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="block space-y-1.5 text-sm font-medium sm:col-span-2">
          Note
          <textarea
            rows={3}
            placeholder="Optional"
            value={draft.note}
            onChange={(e) => update("note", e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <div className="sm:col-span-2">
          <input
            ref={fileInputRef}
            id="wizard-attachments"
            type="file"
            multiple
            // Literal MIME types: WebKitGTK drops extension tokens (see batch-upload).
            accept="application/pdf,image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          />
          <label
            htmlFor="wizard-attachments"
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            <Paperclip className="size-4" aria-hidden />
            {files.length > 0
              ? `Attach ${files.length} document${files.length > 1 ? "s" : ""}`
              : "Attach documents (optional)"}
          </label>
          {files.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              {files.map((file) => (
                <li key={file.name} className="truncate">
                  {file.name}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1.5 text-xs text-muted-foreground">
            Prescriptions and lab reports can be OCR-extracted on the record
            page after creation.
          </p>
        </div>
      </div>

      {(formError || submitError) && (
        <p
          role="alert"
          className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {formError ?? submitError}
        </p>
      )}

      <div className="mt-4 flex items-center justify-end">
        <button
          type="submit"
          disabled={submitting || !canSubmit(draft)}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {submitting && (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          )}
          Create record
        </button>
      </div>
    </form>
  );
}
