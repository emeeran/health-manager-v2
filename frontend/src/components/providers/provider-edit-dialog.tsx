import { Loader2, Pencil } from "lucide-react";
import { useState, type FormEvent } from "react";
import { updateProvider } from "../../lib/api/providers";
import { useEscClose } from "../../hooks/use-esc-close";
import type { Provider } from "../../lib/types/provider";
import { INPUT_CLASS } from "../../lib/utils";

/** Edit dialog for a directory provider: prefilled, PATCH on save.
 * Mirrors the member edit dialog's styling. */
export function ProviderEditDialog({
  provider,
  onClose,
  onSaved,
}: {
  provider: Provider;
  onClose: () => void;
  onSaved: (provider: Provider) => void;
}) {
  const [name, setName] = useState(provider.name);
  const [specialty, setSpecialty] = useState(provider.specialty ?? "");
  const [hospital, setHospital] = useState(provider.hospital ?? "");
  const [phone, setPhone] = useState(provider.phone ?? "");
  const [notes, setNotes] = useState(provider.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Escape closes the dialog (routed through the global overlay stack).
  useEscClose(true, onClose);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const saved = await updateProvider(provider.id, {
        name: name.trim(),
        specialty: specialty || null,
        hospital: hospital || null,
        phone: phone || null,
        notes: notes || null,
      });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save changes.");
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      onClick={onClose}
      data-testid="provider-edit-dialog"
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        aria-label={`Edit ${provider.name}`}
        className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-lg"
      >
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
          <Pencil className="size-4" aria-hidden />
          Edit provider
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1.5 text-sm font-medium">
            Name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Dr Priya Rao"
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Specialty
            <input
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              placeholder="Cardiology"
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Hospital / clinic
            <input
              value={hospital}
              onChange={(e) => setHospital(e.target.value)}
              placeholder="City Hospital"
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Phone
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Optional"
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
            Notes
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
        </div>
        {error && (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {error}
          </p>
        )}
        <div className="mt-4 flex items-center justify-end gap-2">
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
