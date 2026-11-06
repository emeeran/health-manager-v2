import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { Loader2, Plus, Syringe, Trash2, X } from "lucide-react";
import {
  createVaccination,
  deleteVaccination,
  listVaccinations,
} from "../../lib/api/vaccinations";
import {
  isBoosterOverdue,
  type Vaccination,
} from "../../lib/types/vaccination";
import { todayIso, formatDate } from "../../lib/utils";

/** Vaccination list + add form with booster-due tracking. */
export default function VaccinationsSection({
  memberId,
}: {
  memberId: string;
}) {
  const {
    data: vaccinations,
    error: listError,
    isLoading,
    mutate,
  } = useSWR<Vaccination[]>(
    memberId ? ["vaccinations", memberId] : null,
    ([, id]: [string, string]) => listVaccinations(id),
  );
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [dateAdministered, setDateAdministered] = useState(todayIso());
  const [boosterDue, setBoosterDue] = useState("");
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setSaving(true);
    try {
      await createVaccination(memberId, {
        name: name.trim(),
        date_administered: dateAdministered,
        booster_due_date: boosterDue || null,
        notes: notes.trim() || null,
      });
      setName("");
      setBoosterDue("");
      setNotes("");
      setShowForm(false);
      await mutate();
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Could not add the vaccination.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    setFormError(null);
    setDeleting(id);
    try {
      await deleteVaccination(memberId, id);
      await mutate();
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : "Could not delete the vaccination.",
      );
    } finally {
      setDeleting(null);
    }
  }

  const list = vaccinations ?? [];
  const overdueCount = list.filter((v) =>
    isBoosterOverdue(v.booster_due_date),
  ).length;

  return (
    <section aria-label="Vaccinations" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Syringe className="size-5 text-primary" aria-hidden />
          Vaccinations
          {list.length > 0 && (
            <span className="text-sm font-normal text-muted-foreground">
              ({list.length}
              {overdueCount > 0 ? `, ${overdueCount} booster overdue` : ""})
            </span>
          )}
        </h2>
        <button
          type="button"
          aria-expanded={showForm}
          onClick={() => setShowForm((open) => !open)}
          className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
        >
          {showForm ? (
            <X className="size-4" aria-hidden />
          ) : (
            <Plus className="size-4" aria-hidden />
          )}
          {showForm ? "Cancel" : "Add"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleAdd}
          className="space-y-3 rounded-xl border border-border bg-card p-4 shadow-sm"
          aria-label="Add vaccination"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm font-medium">
              Vaccine name
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. IPV booster"
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Date administered
              <input
                type="date"
                required
                value={dateAdministered}
                onChange={(e) => setDateAdministered(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Booster due (optional)
              <input
                type="date"
                value={boosterDue}
                onChange={(e) => setBoosterDue(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Notes (optional)
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
          </div>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {saving && <Loader2 className="size-4 animate-spin" aria-hidden />}
            Save vaccination
          </button>
        </form>
      )}

      {formError && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {formError}
        </p>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading vaccinations…
        </div>
      ) : listError ? (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load vaccinations.{" "}
          {listError instanceof Error ? listError.message : ""}
        </p>
      ) : list.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
          No vaccinations recorded yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {list.map((vaccination) => {
            const overdue = isBoosterOverdue(vaccination.booster_due_date);
            return (
              <li
                key={vaccination.id}
                className={`flex items-center justify-between gap-2 rounded-xl border bg-card px-3 py-2 text-sm shadow-sm ${
                  overdue ? "border-danger/40" : "border-border"
                }`}
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{vaccination.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(vaccination.date_administered)}
                    {vaccination.booster_due_date && (
                      <>
                        {" · booster "}
                        <span
                          className={overdue ? "font-semibold text-danger" : ""}
                        >
                          {overdue ? "overdue since " : ""}
                          {formatDate(vaccination.booster_due_date)}
                        </span>
                      </>
                    )}
                  </p>
                </div>
                <button
                  type="button"
                  aria-label={`Delete ${vaccination.name}`}
                  disabled={deleting === vaccination.id}
                  onClick={() => void handleDelete(vaccination.id)}
                  className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50"
                >
                  {deleting === vaccination.id ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="size-4" aria-hidden />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
