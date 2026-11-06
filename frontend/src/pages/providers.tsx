import {
  Hospital,
  Loader2,
  Pencil,
  Stethoscope,
  Trash2,
  UserRound,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import {
  createProvider,
  deleteProvider,
  listProviders,
} from "../lib/api/providers";
import { ProviderEditDialog } from "../components/providers/provider-edit-dialog";
import type { Provider } from "../lib/types/provider";
import { INPUT_CLASS } from "../lib/utils";

/** Household care directory: doctors and facilities members can be assigned to. */
export default function Providers() {
  const {
    data: providers,
    error,
    isLoading,
    mutate,
  } = useSWR("/providers", listProviders);

  const [editing, setEditing] = useState<Provider | null>(null);

  async function remove(provider: Provider) {
    if (!window.confirm(`Remove ${provider.name} from the directory?`)) return;
    await deleteProvider(provider.id);
    await mutate();
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Stethoscope className="size-6 text-primary" aria-hidden />
          Providers
        </h1>
        <p className="text-sm text-muted-foreground">
          Doctors and facilities for the whole household. Assign them to members
          from a member's page.
        </p>
      </div>

      <AddProviderForm onCreated={() => void mutate()} />

      {isLoading && (
        <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading providers…
        </div>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load providers.{" "}
          {error instanceof Error ? error.message : ""}
        </p>
      )}

      {providers && providers.length === 0 && (
        <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center">
          <p className="text-sm font-medium">No providers yet</p>
          <p className="text-sm text-muted-foreground">
            Add your family's doctors above.
          </p>
        </div>
      )}

      {providers && providers.length > 0 && (
        <ul className="space-y-2">
          {providers.map((provider) => (
            <li
              key={provider.id}
              className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm"
            >
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <UserRound className="size-4.5" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{provider.name}</p>
                <p className="flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                  {provider.specialty && <span>{provider.specialty}</span>}
                  {provider.hospital && (
                    <span className="flex items-center gap-1">
                      <Hospital className="size-3" aria-hidden />
                      {provider.hospital}
                    </span>
                  )}
                  {provider.phone && <span>{provider.phone}</span>}
                </p>
              </div>
              <button
                type="button"
                aria-label={`Edit ${provider.name}`}
                onClick={() => setEditing(provider)}
                className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <Pencil className="size-4" aria-hidden />
              </button>
              <button
                type="button"
                aria-label={`Remove ${provider.name}`}
                onClick={() => void remove(provider)}
                className="rounded-lg p-1.5 text-danger transition-colors hover:bg-danger/10"
              >
                <Trash2 className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <ProviderEditDialog
          provider={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void mutate();
          }}
        />
      )}
    </div>
  );
}

function AddProviderForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [hospital, setHospital] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createProvider({
        name: name.trim(),
        ...(specialty ? { specialty } : {}),
        ...(hospital ? { hospital } : {}),
        ...(phone ? { phone } : {}),
      });
      setName("");
      setSpecialty("");
      setHospital("");
      setPhone("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add provider.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-label="Add provider"
      className="rounded-xl border border-border bg-card p-5 shadow-sm"
    >
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
      </div>
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
        disabled={busy || !name.trim()}
        className="mt-4 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
      >
        {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
        Add provider
      </button>
    </form>
  );
}
