import { AlarmClock, BellRing, Loader2, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import {
  createReminder,
  deleteReminder,
  listReminders,
  setReminderDone,
} from "../../lib/api/reminders";
import {
  REMINDER_REPEATS,
  REMINDER_REPEAT_LABELS,
  type Reminder,
  type ReminderRepeat,
} from "../../lib/types/reminder";
import { INPUT_CLASS, cn } from "../../lib/utils";

/** `datetime-local` value for tomorrow at 09:00, in local time. */
function tomorrowAtNine(): string {
  const due = new Date();
  due.setDate(due.getDate() + 1);
  due.setHours(9, 0, 0, 0);
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${due.getFullYear()}-${pad(due.getMonth() + 1)}-${pad(due.getDate())}` +
    `T${pad(due.getHours())}:${pad(due.getMinutes())}`
  );
}

export default function RemindersSection({ memberId }: { memberId: string }) {
  const {
    data: reminders,
    error,
    isLoading,
    mutate,
  } = useSWR<Reminder[]>("/reminders", listReminders);

  const mine = (reminders ?? [])
    .filter((reminder) => reminder.member_id === memberId)
    .sort(
      (a, b) =>
        new Date(a.remind_at).getTime() - new Date(b.remind_at).getTime(),
    );

  async function handleDone(reminder: Reminder, done: boolean) {
    // Optimistic so the checkbox doesn't lag behind the click.
    await mutate(
      async (current) => {
        await setReminderDone(reminder.id, done);
        return current;
      },
      {
        optimisticData: (current) =>
          (current ?? []).map((r) =>
            r.id === reminder.id ? { ...r, done } : r,
          ),
        rollbackOnError: true,
        revalidate: true,
      },
    );
  }

  async function handleDelete(reminder: Reminder) {
    await mutate(
      async (current) => {
        await deleteReminder(reminder.id);
        return current;
      },
      {
        optimisticData: (current) =>
          (current ?? []).filter((r) => r.id !== reminder.id),
        rollbackOnError: true,
        revalidate: true,
      },
    );
  }

  return (
    <section aria-label="Reminders" className="space-y-4">
      <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
        <AlarmClock className="size-5 text-primary" aria-hidden />
        Reminders
      </h2>

      <AddReminderForm
        memberId={memberId}
        onCreated={() => {
          void mutate();
        }}
      />

      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load reminders.{" "}
          {error instanceof Error ? error.message : ""}
        </p>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading reminders…
        </div>
      ) : mine.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          No reminders for this member yet. Add one above.
        </p>
      ) : (
        <ul className="space-y-2">
          {mine.map((reminder) => {
            const overdue = !reminder.done && isOverdue(reminder.remind_at);
            return (
              <li
                key={reminder.id}
                className={cn(
                  "flex items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-sm",
                  overdue ? "border-warning/50 bg-warning/5" : "border-border",
                )}
              >
                <input
                  type="checkbox"
                  checked={reminder.done}
                  onChange={(e) => void handleDone(reminder, e.target.checked)}
                  aria-label={
                    reminder.done
                      ? `Mark ${reminder.title} not done`
                      : `Mark ${reminder.title} done`
                  }
                  className="size-4 shrink-0 accent-primary"
                />
                <span className="min-w-0 flex-1">
                  <span
                    className={cn(
                      "block truncate text-sm font-medium",
                      reminder.done && "text-muted-foreground line-through",
                    )}
                  >
                    {reminder.title}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {formatDateTime(reminder.remind_at)}
                    {reminder.repeat !== "none" &&
                      ` · ${REMINDER_REPEAT_LABELS[reminder.repeat]}`}
                  </span>
                </span>
                {overdue && (
                  <span className="flex shrink-0 items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning-foreground">
                    <BellRing className="size-3" aria-hidden />
                    Overdue
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => void handleDelete(reminder)}
                  aria-label={`Delete reminder ${reminder.title}`}
                  className="shrink-0 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger"
                >
                  <Trash2 className="size-4" aria-hidden />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function isOverdue(remindAt: string): boolean {
  const due = new Date(remindAt).getTime();
  return !Number.isNaN(due) && due < Date.now();
}

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE_FORMAT.format(date);
}

function AddReminderForm({
  memberId,
  onCreated,
}: {
  memberId: string;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [remindAt, setRemindAt] = useState(tomorrowAtNine);
  const [repeat, setRepeat] = useState<ReminderRepeat>("none");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const due = new Date(remindAt);
    if (!title.trim() || Number.isNaN(due.getTime())) {
      setError("Give the reminder a title and a valid date.");
      return;
    }
    setSubmitting(true);
    try {
      await createReminder({
        title: title.trim(),
        member_id: memberId,
        remind_at: due.toISOString(),
        repeat,
      });
      setTitle("");
      setRemindAt(tomorrowAtNine());
      setRepeat("none");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add reminder.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border bg-card p-4 shadow-sm"
      aria-label="Add reminder"
    >
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Plus className="size-4 text-primary" aria-hidden />
        Add reminder
      </h3>
      <div className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1.5 text-sm font-medium lg:col-span-2">
          Title
          <input
            required
            placeholder="e.g. Refill statin prescription"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Remind at
          <input
            type="datetime-local"
            required
            value={remindAt}
            onChange={(e) => setRemindAt(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Repeat
          <select
            value={repeat}
            onChange={(e) => setRepeat(e.target.value as ReminderRepeat)}
            className={INPUT_CLASS}
          >
            {REMINDER_REPEATS.map((value) => (
              <option key={value} value={value}>
                {REMINDER_REPEAT_LABELS[value]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        type="submit"
        disabled={submitting}
        className="mt-3 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
      >
        {submitting && <Loader2 className="size-4 animate-spin" aria-hidden />}
        Add reminder
      </button>
      {error && (
        <p
          role="alert"
          className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}
    </form>
  );
}
