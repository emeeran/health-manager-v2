import { Check, Loader2, Pencil, Pill, Plus, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import {
  createMedication,
  deleteMedication,
  updateMedication,
} from "../../lib/api/medications";
import { listProviders } from "../../lib/api/providers";
import { useEscClose } from "../../hooks/use-esc-close";
import {
  DEFAULT_SLOT_TIMES,
  DOSE_FORMS,
  MEDICATION_SLOTS,
  MEDICATION_STATUSES,
  SCHEDULE_TYPES,
  SCHEDULE_TYPE_LABELS,
  SLOT_LABELS,
  doseFormClass,
  medicationDurationLabel,
  medicationSlotTime,
  usedMedicationSlots,
  type Medication,
  type MedicationSlot,
  type MedicationStatus,
  type ScheduleType,
} from "../../lib/types/medication";
import { INPUT_CLASS, cn, todayIso } from "../../lib/utils";

export function MedicationManager({
  memberId,
  medications,
  isLoading,
  onChange,
}: {
  memberId: string;
  medications?: Medication[];
  isLoading: boolean;
  onChange: () => void;
}) {
  const active = (medications ?? []).filter((med) => med.status === "active");
  // Entry form stays collapsed so the page leads with the schedule table;
  // the same reveal pattern as vaccinations/conditions.
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Medication | null>(null);
  // One column per slot actually in use, canonical morning→bedtime order.
  const slots = usedMedicationSlots(active);

  return (
    <section aria-label="Manage medicines" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Pill className="size-5 text-primary" aria-hidden />
          Medicine schedule
        </h2>
        <button
          type="button"
          aria-expanded={formOpen}
          onClick={() => setFormOpen((open) => !open)}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
        >
          {formOpen ? (
            <X className="size-4" aria-hidden />
          ) : (
            <Plus className="size-4 text-primary" aria-hidden />
          )}
          {formOpen ? "Cancel" : "Add medicine"}
        </button>
      </div>

      {formOpen && (
        <AddMedicationForm
          memberId={memberId}
          onCreated={() => {
            onChange();
            setFormOpen(false);
          }}
        />
      )}

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading medicines…
        </div>
      ) : active.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          No active medicines for this member.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
          {/* The v1-style schedule table: one row per medicine, one column
              per dose time, editable in place. */}
          <table className="w-full text-xs" aria-label="Medicine schedule">
            <thead>
              <tr className="border-b border-border text-left uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2 font-semibold">Type</th>
                <th className="px-3 py-2 font-semibold">Medicine</th>
                {slots.map((slot) => (
                  <th key={slot} className="px-2 py-2 font-semibold">
                    {SLOT_LABELS[slot]}
                  </th>
                ))}
                <th className="px-2 py-2 font-semibold">Food</th>
                <th className="px-2 py-2 font-semibold">Duration</th>
                <th className="px-3 py-2 font-semibold">Rx by</th>
                <th className="px-3 py-2 font-semibold" aria-label="Actions" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {active.map((med) => (
                <MedicationRow
                  key={med.id}
                  memberId={memberId}
                  medication={med}
                  slots={slots}
                  onChange={onChange}
                  onEdit={() => setEditing(med)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <EditMedicationDialog
          key={editing.id}
          memberId={memberId}
          medication={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChange();
          }}
        />
      )}
    </section>
  );
}

const SCHEDULE_BADGES: Record<ScheduleType, string> = {
  daily: "bg-primary/10 text-primary",
  prn: "bg-muted text-muted-foreground",
  taper: "bg-warning/15 text-warning-foreground",
  cycle: "bg-primary/10 text-primary",
};

function MedicationRow({
  memberId,
  medication,
  slots,
  onChange,
  onEdit,
}: {
  memberId: string;
  medication: Medication;
  slots: MedicationSlot[];
  onChange: () => void;
  onEdit: () => void;
}) {
  const [busy, setBusy] = useState<"delete" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    if (
      !window.confirm(`Delete ${medication.medicine}? This cannot be undone.`)
    )
      return;
    setBusy("delete");
    setError(null);
    try {
      await deleteMedication(memberId, medication.id);
      onChange();
    } catch {
      setError("Delete failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <tr>
      <td className="px-3 py-2">
        <span
          className={cn(
            "rounded-full px-2 py-0.5 font-medium",
            doseFormClass(medication.dose_form),
          )}
        >
          {medication.dose_form ?? "—"}
        </span>
      </td>
      <td className="min-w-0 px-3 py-2">
        <p className="truncate text-sm font-semibold uppercase">
          {medication.medicine}
        </p>
        <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          {medication.dosage && <span>{medication.dosage}</span>}
          {medication.schedule_type !== "daily" && (
            <span
              className={cn(
                "rounded-full px-2 py-0.5 font-medium capitalize",
                SCHEDULE_BADGES[medication.schedule_type],
              )}
            >
              {SCHEDULE_TYPE_LABELS[medication.schedule_type]}
            </span>
          )}
        </p>
      </td>
      {slots.map((slot) => (
        <td
          key={slot}
          className="whitespace-nowrap px-2 py-2 text-center font-mono font-medium tabular-nums"
        >
          {medication.schedule_json?.slots?.includes(slot) ? (
            medicationSlotTime(medication, slot)
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
      ))}
      <td
        className="max-w-[8rem] truncate px-2 py-2 text-muted-foreground"
        title={medication.timing ?? undefined}
      >
        {medication.timing || "—"}
      </td>
      <td className="whitespace-nowrap px-2 py-2 text-muted-foreground">
        {medicationDurationLabel(medication)}
      </td>
      <td
        className="max-w-[10rem] truncate px-3 py-2 text-muted-foreground"
        title={medication.provider_name ?? undefined}
      >
        {medication.provider_name || "—"}
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center justify-end gap-1">
          {error && (
            <span role="alert" className="text-xs text-danger">
              {error}
            </span>
          )}
          <button
            type="button"
            onClick={onEdit}
            aria-label={`Edit ${medication.medicine}`}
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Pencil className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => void remove()}
            disabled={busy !== null}
            aria-label={`Delete ${medication.medicine}`}
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50"
          >
            {busy === "delete" ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Trash2 className="size-4" aria-hidden />
            )}
          </button>
        </div>
      </td>
    </tr>
  );
}

/**
 * Edit dialog for one row of the schedule table: prefilled from the current
 * medicine, PATCH on save. Slot edits rebuild the schedule server-side
 * (taper/cycle params are preserved there).
 */
function EditMedicationDialog({
  memberId,
  medication,
  onClose,
  onSaved,
}: {
  memberId: string;
  medication: Medication;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [medicine, setMedicine] = useState(medication.medicine);
  const [doseForm, setDoseForm] = useState(medication.dose_form ?? "");
  const [dosage, setDosage] = useState(medication.dosage ?? "");
  const [timing, setTiming] = useState(medication.timing ?? "");
  const [durationDays, setDurationDays] = useState(
    medication.duration_days?.toString() ?? "",
  );
  const [provider, setProvider] = useState(medication.provider_name ?? "");
  const [status, setStatus] = useState<MedicationStatus>(medication.status);
  const [slots, setSlots] = useState<MedicationSlot[]>(
    (medication.schedule_json?.slots ?? []) as MedicationSlot[],
  );
  const [slotTimes, setSlotTimes] = useState<Record<MedicationSlot, string>>({
    ...DEFAULT_SLOT_TIMES,
    ...medication.schedule_json?.slot_times,
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Escape closes the dialog (routed through the global overlay stack).
  useEscClose(true, onClose);

  function toggleSlot(slot: MedicationSlot) {
    setSlots((current) =>
      current.includes(slot)
        ? current.filter((value) => value !== slot)
        : [...current, slot].sort(
            (a, b) => MEDICATION_SLOTS.indexOf(a) - MEDICATION_SLOTS.indexOf(b),
          ),
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const assignedTimes = Object.fromEntries(
        MEDICATION_SLOTS.filter((slot) => slots.includes(slot)).map((slot) => [
          slot,
          slotTimes[slot],
        ]),
      );
      await updateMedication(memberId, medication.id, {
        medicine,
        dose_form: doseForm || null,
        dosage: dosage || null,
        timing: timing || null,
        duration_days: durationDays ? Number(durationDays) : null,
        provider_name: provider || null,
        status,
        ...(medication.schedule_type !== "prn"
          ? { slots, slot_times: assignedTimes }
          : {}),
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save changes.");
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        aria-label={`Edit ${medication.medicine}`}
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-border bg-card p-5 shadow-lg"
      >
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
          <Pencil className="size-4" aria-hidden />
          Edit medicine
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1.5 text-sm font-medium">
            Name
            <input
              required
              value={medicine}
              onChange={(e) => setMedicine(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Type
            <select
              value={doseForm}
              onChange={(e) => setDoseForm(e.target.value)}
              className={INPUT_CLASS}
            >
              <option value="">Optional</option>
              {DOSE_FORMS.map((form) => (
                <option key={form} value={form}>
                  {form}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Dosage
            <input
              placeholder="e.g. 500 mg"
              value={dosage}
              onChange={(e) => setDosage(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Food
            <input
              placeholder="e.g. after food"
              value={timing}
              onChange={(e) => setTiming(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Duration (days)
            <input
              type="number"
              min={1}
              placeholder="Until next review"
              value={durationDays}
              onChange={(e) => setDurationDays(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Prescribed by
            <input
              placeholder="Optional"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Status
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as MedicationStatus)}
              className={INPUT_CLASS}
            >
              {MEDICATION_STATUSES.map((value) => (
                <option key={value} value={value} className="capitalize">
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>

        {medication.schedule_type !== "prn" && (
          <fieldset className="mt-3">
            <legend className="mb-1.5 text-sm font-medium">
              Dose times — pick the slots and set each clock time
            </legend>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {MEDICATION_SLOTS.map((slot) => {
                const selected = slots.includes(slot);
                return (
                  <div
                    key={slot}
                    className={cn(
                      "flex items-center gap-2 rounded-lg border px-2.5 py-1.5 transition-colors",
                      selected
                        ? "border-primary bg-primary/5"
                        : "border-border",
                    )}
                  >
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={selected}
                      aria-label={SLOT_LABELS[slot]}
                      onClick={() => toggleSlot(slot)}
                      className={cn(
                        "flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
                        selected
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-input bg-background",
                      )}
                    >
                      {selected && <Check className="size-3" aria-hidden />}
                    </button>
                    <span
                      className={cn(
                        "min-w-0 flex-1 truncate text-xs font-medium",
                        !selected && "text-muted-foreground",
                      )}
                    >
                      {SLOT_LABELS[slot]}
                    </span>
                    <input
                      type="time"
                      value={slotTimes[slot]}
                      onChange={(e) =>
                        setSlotTimes((current) => ({
                          ...current,
                          [slot]: e.target.value,
                        }))
                      }
                      disabled={!selected}
                      aria-label={`${SLOT_LABELS[slot]} dose time`}
                      className={cn(
                        "w-24 rounded-md border border-input bg-background px-1.5 py-1 font-mono text-xs tabular-nums outline-none focus:ring-2 focus:ring-ring",
                        !selected && "opacity-40",
                      )}
                    />
                  </div>
                );
              })}
            </div>
          </fieldset>
        )}

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {error}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {submitting && (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            )}
            Save changes
          </button>
        </div>
      </form>
    </div>
  );
}

function AddMedicationForm({
  memberId,
  onCreated,
}: {
  memberId: string;
  onCreated: () => void;
}) {
  const [medicine, setMedicine] = useState("");
  const [doseForm, setDoseForm] = useState("");
  const [dosage, setDosage] = useState("");
  const [timing, setTiming] = useState("");
  const [durationDays, setDurationDays] = useState("");
  const [startDate, setStartDate] = useState(todayIso());
  const [scheduleType, setScheduleType] = useState<ScheduleType>("daily");
  const [slots, setSlots] = useState<MedicationSlot[]>(["morning"]);
  const [slotTimes, setSlotTimes] =
    useState<Record<MedicationSlot, string>>(DEFAULT_SLOT_TIMES);
  const [providerId, setProviderId] = useState("");
  const { data: providers } = useSWR("providers", listProviders);
  const [taperStart, setTaperStart] = useState("");
  const [taperStep, setTaperStep] = useState("");
  const [taperEveryDays, setTaperEveryDays] = useState("");
  const [taperFloor, setTaperFloor] = useState("");
  const [cycleOn, setCycleOn] = useState("");
  const [cycleOff, setCycleOff] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Rarely-used fields live behind a disclosure so the common path —
  // name, dose, schedule — stays one short grid.
  const [showMore, setShowMore] = useState(false);

  // The toggles are the source of truth for which slots are submitted;
  // each assigned slot carries its editable clock time.
  function toggleSlot(slot: MedicationSlot) {
    setSlots((current) =>
      current.includes(slot)
        ? current.filter((value) => value !== slot)
        : [...current, slot].sort(
            (a, b) => MEDICATION_SLOTS.indexOf(a) - MEDICATION_SLOTS.indexOf(b),
          ),
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (scheduleType === "taper") {
      const required = [taperStart, taperStep, taperEveryDays, taperFloor];
      if (
        required.some(
          (value) => value === "" || !Number.isFinite(Number(value)),
        )
      ) {
        setError("Fill in all taper parameters with numbers.");
        return;
      }
    }
    if (scheduleType === "cycle") {
      const onDays = Number(cycleOn);
      const offDays = Number(cycleOff);
      if (
        !Number.isFinite(onDays) ||
        !Number.isFinite(offDays) ||
        !Number.isInteger(onDays) ||
        !Number.isInteger(offDays) ||
        onDays < 1 ||
        offDays < 1
      ) {
        setError("On/off days must be positive whole numbers.");
        return;
      }
    }
    setSubmitting(true);
    try {
      // Every assigned slot carries its clock time so the dose rings at
      // exactly the time shown, not the household default.
      const assignedTimes = Object.fromEntries(
        MEDICATION_SLOTS.filter((slot) => slots.includes(slot)).map((slot) => [
          slot,
          slotTimes[slot],
        ]),
      );
      await createMedication(memberId, {
        medicine,
        ...(doseForm ? { dose_form: doseForm } : {}),
        ...(dosage ? { dosage } : {}),
        ...(timing ? { timing } : {}),
        ...(durationDays ? { duration_days: Number(durationDays) } : {}),
        ...(startDate ? { start_date: startDate } : {}),
        schedule_type: scheduleType,
        ...(scheduleType !== "prn" && slots.length > 0 ? { slots } : {}),
        ...(scheduleType !== "prn" && slots.length > 0
          ? { slot_times: assignedTimes }
          : {}),
        ...(providerId
          ? {
              provider_name: providers?.find((p) => p.id === providerId)?.name,
            }
          : {}),
        ...(scheduleType === "taper"
          ? {
              taper: {
                doses_start: Number(taperStart),
                step: Number(taperStep),
                step_every_days: Number(taperEveryDays),
                floor: Number(taperFloor),
              },
            }
          : {}),
        ...(scheduleType === "cycle"
          ? { cycle: { on_days: Number(cycleOn), off_days: Number(cycleOff) } }
          : {}),
      });
      setMedicine("");
      setDoseForm("");
      setDosage("");
      setTiming("");
      setDurationDays("");
      setSlots(["morning"]);
      setSlotTimes(DEFAULT_SLOT_TIMES);
      setProviderId("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add medicine.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border bg-card p-4 shadow-sm"
      aria-label="Add medicine"
    >
      <div className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="space-y-1.5 text-sm font-medium">
          Name
          <input
            required
            placeholder="e.g. Metformin"
            value={medicine}
            onChange={(e) => setMedicine(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Type
          <select
            value={doseForm}
            onChange={(e) => setDoseForm(e.target.value)}
            className={INPUT_CLASS}
          >
            <option value="">Optional</option>
            {DOSE_FORMS.map((form) => (
              <option key={form} value={form}>
                {form}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Dosage
          <input
            placeholder="e.g. 500 mg"
            value={dosage}
            onChange={(e) => setDosage(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Food
          <input
            placeholder="e.g. after food"
            value={timing}
            onChange={(e) => setTiming(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Schedule
          <select
            value={scheduleType}
            onChange={(e) => setScheduleType(e.target.value as ScheduleType)}
            className={INPUT_CLASS}
          >
            {SCHEDULE_TYPES.map((type) => (
              <option key={type} value={type}>
                {SCHEDULE_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-3">
        <button
          type="button"
          aria-expanded={showMore}
          onClick={() => setShowMore((open) => !open)}
          className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          {showMore ? "− Fewer options" : "+ More options"}
        </button>
        {showMore && (
          <div className="mt-3 grid items-end gap-3 sm:grid-cols-3">
            <label className="space-y-1.5 text-sm font-medium">
              Prescribed by
              <select
                value={providerId}
                onChange={(e) => setProviderId(e.target.value)}
                className={INPUT_CLASS}
              >
                <option value="">Optional</option>
                {(providers ?? []).map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Duration (days)
              <input
                type="number"
                min={1}
                placeholder="Optional"
                value={durationDays}
                onChange={(e) => setDurationDays(e.target.value)}
                className={INPUT_CLASS}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Start date
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className={INPUT_CLASS}
              />
            </label>
          </div>
        )}
      </div>

      {scheduleType !== "prn" && (
        <fieldset className="mt-3">
          <legend className="mb-1.5 text-sm font-medium">
            Timing — pick the slots and set each dose time
          </legend>
          <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
            {MEDICATION_SLOTS.map((slot) => {
              const selected = slots.includes(slot);
              return (
                <div
                  key={slot}
                  className={cn(
                    "flex items-center gap-2 rounded-lg border px-2.5 py-1.5 transition-colors",
                    selected ? "border-primary bg-primary/5" : "border-border",
                  )}
                >
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={selected}
                    aria-label={SLOT_LABELS[slot]}
                    onClick={() => toggleSlot(slot)}
                    className={cn(
                      "flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
                      selected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-input bg-background",
                    )}
                  >
                    {selected && <Check className="size-3" aria-hidden />}
                  </button>
                  <span
                    className={cn(
                      "min-w-0 flex-1 truncate text-xs font-medium",
                      !selected && "text-muted-foreground",
                    )}
                  >
                    {SLOT_LABELS[slot]}
                  </span>
                  <input
                    type="time"
                    value={slotTimes[slot]}
                    onChange={(e) =>
                      setSlotTimes((current) => ({
                        ...current,
                        [slot]: e.target.value,
                      }))
                    }
                    disabled={!selected}
                    aria-label={`${SLOT_LABELS[slot]} dose time`}
                    className={cn(
                      "w-24 rounded-md border border-input bg-background px-1.5 py-1 font-mono text-xs tabular-nums outline-none focus:ring-2 focus:ring-ring",
                      !selected && "opacity-40",
                    )}
                  />
                </div>
              );
            })}
          </div>
        </fieldset>
      )}

      {scheduleType === "taper" && (
        <div className="mt-3 grid items-end gap-3 sm:grid-cols-4">
          <label className="space-y-1.5 text-sm font-medium">
            Starting doses
            <input
              type="number"
              min={0}
              step="any"
              required
              value={taperStart}
              onChange={(e) => setTaperStart(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Step (−doses)
            <input
              type="number"
              min={0}
              step="any"
              required
              value={taperStep}
              onChange={(e) => setTaperStep(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Every (days)
            <input
              type="number"
              min={1}
              required
              value={taperEveryDays}
              onChange={(e) => setTaperEveryDays(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Floor
            <input
              type="number"
              min={0}
              step="any"
              required
              value={taperFloor}
              onChange={(e) => setTaperFloor(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
        </div>
      )}

      {scheduleType === "cycle" && (
        <div className="mt-3 grid items-end gap-3 sm:grid-cols-2">
          <label className="space-y-1.5 text-sm font-medium">
            Days on
            <input
              type="number"
              min={1}
              required
              value={cycleOn}
              onChange={(e) => setCycleOn(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Days off
            <input
              type="number"
              min={1}
              required
              value={cycleOff}
              onChange={(e) => setCycleOff(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
        </div>
      )}

      {error && (
        <p
          role="alert"
          className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={submitting}
        className="mt-4 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
      >
        {submitting && <Loader2 className="size-4 animate-spin" aria-hidden />}
        Add medicine
      </button>
    </form>
  );
}
