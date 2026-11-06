import { Loader2, Trash2, UserPlus, Users } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import useSWR from "swr";
import { createMember, deleteMember } from "../lib/api/members";
import { RELATIONSHIPS, type Member } from "../lib/types/member";

function formatBirthDate(value: string | null): string {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return month && day ? `${year}-${month}-${day}` : value;
}

export default function Members() {
  const {
    data: members,
    error,
    isLoading,
    mutate,
  } = useSWR<Member[]>("/members");

  if (error) {
    return (
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Members</h1>
        <p
          role="alert"
          className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load members. {error instanceof Error ? error.message : ""}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Members</h1>
        <p className="text-sm text-muted-foreground">
          People whose health records you manage.
        </p>
      </div>

      <CreateMemberForm
        onCreated={() => {
          void mutate();
        }}
      />

      <section
        className="rounded-xl border border-border bg-card shadow-sm"
        aria-label="Member list"
      >
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Loading members…
          </div>
        ) : !members || members.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-10 text-center">
            <Users className="size-8 text-muted-foreground" aria-hidden />
            <p className="text-sm font-medium">No members yet</p>
            <p className="text-sm text-muted-foreground">
              Add your first family member above.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {members.map((member) => (
              <li
                key={member.id}
                className="flex items-center gap-4 px-5 py-3.5"
              >
                <Link
                  to={`/members/${member.id}`}
                  className="flex min-w-0 flex-1 items-center gap-4"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary">
                    {member.name.charAt(0).toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {member.name}
                    </p>
                    <p className="text-xs capitalize text-muted-foreground">
                      {member.relationship}
                      {member.birth_date
                        ? ` · born ${formatBirthDate(member.birth_date)}`
                        : ""}
                    </p>
                  </div>
                </Link>
                <DeleteMemberButton
                  id={member.id}
                  name={member.name}
                  onDeleted={() => void mutate()}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function CreateMemberForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState<string>("self");
  const [birthDate, setBirthDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await createMember({
        name,
        relationship,
        ...(birthDate ? { birth_date: birthDate } : {}),
      });
      setName("");
      setBirthDate("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add member.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border bg-card p-5 shadow-sm"
      aria-label="Add member"
    >
      <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
        <UserPlus className="size-4" aria-hidden />
        Add a member
      </h2>
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
        <input
          required
          placeholder="Full name"
          aria-label="Full name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <select
          aria-label="Relationship"
          value={relationship}
          onChange={(e) => setRelationship(e.target.value)}
          className="rounded-lg border border-input bg-background px-3 py-2 text-sm capitalize outline-none focus:ring-2 focus:ring-ring"
        >
          {RELATIONSHIPS.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <input
          type="date"
          aria-label="Birth date (optional)"
          value={birthDate}
          onChange={(e) => setBirthDate(e.target.value)}
          className="rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {/* Medical / family histories live in the member's profile (edit
          dialog) only — the quick-add stays minimal. */}

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
        Add member
      </button>
    </form>
  );
}

function DeleteMemberButton({
  id,
  name,
  onDeleted,
}: {
  id: string;
  name: string;
  onDeleted: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(false);

  async function handleDelete() {
    if (!window.confirm(`Remove ${name} from your family members?`)) return;
    setDeleting(true);
    setError(false);
    try {
      await deleteMember(id);
      onDeleted();
    } catch {
      setError(true);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {error && (
        <span role="alert" className="text-xs text-danger">
          Delete failed
        </span>
      )}
      <button
        type="button"
        onClick={handleDelete}
        disabled={deleting}
        aria-label={`Delete ${name}`}
        className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50"
      >
        {deleting ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <Trash2 className="size-4" aria-hidden />
        )}
      </button>
    </div>
  );
}
