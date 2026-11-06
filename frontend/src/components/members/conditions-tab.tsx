import { useState, type FormEvent } from "react";
import useSWR from "swr";
import {
  Activity,
  CheckCircle2,
  Loader2,
  Plus,
  Stethoscope,
  Trash2,
  X,
} from "lucide-react";
import {
  createCondition,
  deleteCondition,
  linkMedicationToCondition,
  linkRecordToCondition,
  listConditions,
  updateCondition,
} from "../../lib/api/conditions";
import { listMedications } from "../../lib/api/medications";
import { listRecords } from "../../lib/api/records";
import { recordTypeMeta } from "../../lib/record-types";
import {
  validateConditionCourse,
  CONDITION_STATUSES,
  CONDITION_STATUS_STYLES,
  type ConditionEpisode,
  type ConditionStatus,
  type ConditionUpdateInput,
} from "../../lib/types/condition";
import { INPUT_CLASS, todayIso } from "../../lib/utils";

/**
 * Conditions tab — the member's problem list: condition episodes CRUD with
 * status transitions, plus record/medication linking per episode.
 */
export function ConditionsTab({ memberId }: { memberId: string }) {
  const {
    data: conditions,
    error: listError,
    isLoading,
    mutate,
  } = useSWR<ConditionEpisode[]>(
    memberId ? ["conditions", memberId] : null,
    ([, id]: [string, string]) => listConditions(id),
  );

  return (
    <div className="space-y-6">
      <section aria-label="Condition episodes" className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Activity className="size-5 text-primary" aria-hidden />
          Conditions
        </h2>

        <AddConditionForm memberId={memberId} onAdded={() => void mutate()} />

        {isLoading ? (
          <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Loading conditions…
          </div>
        ) : listError ? (
          <p
            role="alert"
            className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            Could not load conditions.{" "}
            {listError instanceof Error ? listError.message : ""}
          </p>
        ) : (conditions ?? []).length === 0 ? (
          <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
            No condition episodes recorded.
          </p>
        ) : (
          <ul className="space-y-3">
            {(conditions ?? []).map((condition) => (
              <li key={condition.id}>
                <ConditionCard
                  memberId={memberId}
                  condition={condition}
                  onChanged={() => void mutate()}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function AddConditionForm({
  memberId,
  onAdded,
}: {
  memberId: string;
  onAdded: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [icd10, setIcd10] = useState("");
  const [status, setStatus] = useState<ConditionStatus>("active");
  const [onsetDate, setOnsetDate] = useState(todayIso());
  const [resolutionDate, setResolutionDate] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = {
      name: name.trim(),
      icd10_code: icd10.trim() || null,
      status,
      onset_date: onsetDate || null,
      resolution_date: resolutionDate || null,
      notes: notes.trim() || null,
    };
    const validation = validateConditionCourse(input);
    if (validation) {
      setError(validation);
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await createCondition(memberId, input);
      setName("");
      setIcd10("");
      setStatus("active");
      setOnsetDate(todayIso());
      setResolutionDate("");
      setNotes("");
      setOpen(false);
      onAdded();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not add the condition.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1.5 text-sm font-medium text-primary transition-opacity hover:opacity-80"
      >
        {open ? (
          <X className="size-4" aria-hidden />
        ) : (
          <Plus className="size-4" aria-hidden />
        )}
        {open ? "Cancel" : "Add condition episode"}
      </button>
      {open && (
        <form
          onSubmit={handleSubmit}
          className="mt-3 space-y-3"
          aria-label="Add condition"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm font-medium">
              Name
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Type 2 diabetes"
                className={INPUT_CLASS}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              ICD-10 code (optional)
              <input
                value={icd10}
                onChange={(e) => setIcd10(e.target.value)}
                placeholder="e.g. E11.9"
                className={INPUT_CLASS}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Status
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as ConditionStatus)}
                className={INPUT_CLASS}
              >
                {CONDITION_STATUSES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Onset date
              <input
                type="date"
                value={onsetDate}
                onChange={(e) => setOnsetDate(e.target.value)}
                className={INPUT_CLASS}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Resolution date
              {status === "resolved" ? " (required)" : " (optional)"}
              <input
                type="date"
                value={resolutionDate}
                onChange={(e) => setResolutionDate(e.target.value)}
                className={INPUT_CLASS}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Notes (optional)
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className={INPUT_CLASS}
              />
            </label>
          </div>
          {error && (
            <p
              role="alert"
              className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {saving && <Loader2 className="size-4 animate-spin" aria-hidden />}
            Save condition
          </button>
        </form>
      )}
    </div>
  );
}

function ConditionCard({
  memberId,
  condition,
  onChanged,
}: {
  memberId: string;
  condition: ConditionEpisode;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, fallback: string) {
    setError(null);
    setBusy(true);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  function transitionStatus(next: ConditionStatus) {
    const patch: ConditionUpdateInput = { status: next };
    if (next === "resolved" && !condition.resolution_date) {
      // Resolved requires a resolution date — default to today.
      patch.resolution_date = todayIso();
    }
    void run(
      () => updateCondition(memberId, condition.id, patch),
      "Status update failed.",
    );
  }

  async function handleDelete() {
    if (
      !window.confirm(
        `Delete condition "${condition.name}"? Linked records and medications are kept.`,
      )
    ) {
      return;
    }
    await run(() => deleteCondition(memberId, condition.id), "Delete failed.");
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {condition.name}
            {condition.icd10_code && (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
                ICD-10: {condition.icd10_code}
              </span>
            )}
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${CONDITION_STATUS_STYLES[condition.status]}`}
            >
              {condition.status}
            </span>
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {condition.onset_date
              ? `onset ${condition.onset_date}`
              : "onset unknown"}
            {condition.resolution_date
              ? ` · resolved ${condition.resolution_date}`
              : ""}
            {" · "}
            {condition.record_count} records · {condition.medication_count}{" "}
            medications
          </p>
          {condition.notes && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {condition.notes}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            disabled={busy}
            onClick={() => setEditing((value) => !value)}
            className="rounded-lg px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {editing ? "Close" : "Manage"}
          </button>
          <button
            type="button"
            aria-label={`Delete ${condition.name}`}
            disabled={busy}
            onClick={() => void handleDelete()}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger"
          >
            <Trash2 className="size-4" aria-hidden />
          </button>
        </div>
      </div>

      {/* Status transitions */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {CONDITION_STATUSES.filter((status) => status !== condition.status).map(
          (status) => (
            <button
              key={status}
              type="button"
              disabled={busy}
              onClick={() => transitionStatus(status)}
              className="rounded-full border border-border px-2.5 py-1 text-xs capitalize text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              → {status}
            </button>
          ),
        )}
      </div>

      {editing && (
        <div className="mt-3 space-y-3 border-t border-border pt-3">
          <LinkedRecords
            memberId={memberId}
            condition={condition}
            onChanged={onChanged}
          />
          <LinkedMedications
            memberId={memberId}
            condition={condition}
            onChanged={onChanged}
          />
        </div>
      )}

      {error && (
        <p
          role="alert"
          className="mt-2 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function LinkedRecords({
  memberId,
  condition,
  onChanged,
}: {
  memberId: string;
  condition: ConditionEpisode;
  onChanged: () => void;
}) {
  const [linkError, setLinkError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [recordId, setRecordId] = useState("");

  async function link() {
    if (!recordId) return;
    setLinkError(null);
    setBusy(true);
    try {
      await linkRecordToCondition(memberId, condition.id, recordId);
      setRecordId("");
      onChanged();
    } catch (err) {
      setLinkError(err instanceof Error ? err.message : "Link failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
        <Stethoscope className="size-3.5" aria-hidden />
        Linked records ({condition.record_count})
      </p>
      <div className="flex gap-2">
        <RecordLinkSelect
          memberId={memberId}
          value={recordId}
          onChange={setRecordId}
        />
        <button
          type="button"
          disabled={busy || !recordId}
          onClick={() => void link()}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
        >
          {busy ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <Plus className="size-3.5" aria-hidden />
          )}
          Link record
        </button>
      </div>
      {linkError && (
        <p role="alert" className="text-xs text-danger">
          {linkError}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Re-linking a record to another episode moves the link automatically.
      </p>
    </div>
  );
}

function RecordLinkSelect({
  memberId,
  value,
  onChange,
}: {
  memberId: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { data: records } = useSWR(
    memberId ? ["all-records", memberId] : null,
    ([, id]: [string, string]) => listRecords(id, { limit: 100 }),
  );
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Record to link"
      className="min-w-0 flex-1 rounded-lg border border-input bg-background px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
    >
      <option value="">Choose a record…</option>
      {(records ?? []).map((record) => (
        <option key={record.id} value={record.id}>
          {recordTypeMeta(record.record_type).label} · {record.record_date}
          {record.diagnosis ? ` · ${record.diagnosis}` : ""}
        </option>
      ))}
    </select>
  );
}

function LinkedMedications({
  memberId,
  condition,
  onChanged,
}: {
  memberId: string;
  condition: ConditionEpisode;
  onChanged: () => void;
}) {
  const { data: medications } = useSWR(
    memberId ? ["medications-all", memberId] : null,
    ([, id]: [string, string]) => listMedications(id),
  );
  const [medicationId, setMedicationId] = useState("");
  const [linkError, setLinkError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function link() {
    if (!medicationId) return;
    setLinkError(null);
    setBusy(true);
    try {
      await linkMedicationToCondition(memberId, condition.id, medicationId);
      setMedicationId("");
      onChanged();
    } catch (err) {
      setLinkError(err instanceof Error ? err.message : "Link failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
        <CheckCircle2 className="size-3.5" aria-hidden />
        Linked medications ({condition.medication_count})
      </p>
      <div className="flex gap-2">
        <select
          value={medicationId}
          onChange={(e) => setMedicationId(e.target.value)}
          aria-label="Medication to link"
          className="min-w-0 flex-1 rounded-lg border border-input bg-background px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Choose a medication…</option>
          {(medications ?? []).map((medication) => (
            <option key={medication.id} value={medication.id}>
              {medication.medicine}
              {medication.dosage ? ` · ${medication.dosage}` : ""}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy || !medicationId}
          onClick={() => void link()}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
        >
          {busy ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <Plus className="size-3.5" aria-hidden />
          )}
          Link medication
        </button>
      </div>
      {linkError && (
        <p role="alert" className="text-xs text-danger">
          {linkError}
        </p>
      )}
    </div>
  );
}
