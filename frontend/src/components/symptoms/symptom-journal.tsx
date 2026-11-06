import { useMemo, useState } from "react";
import useSWR from "swr";
import { Activity, Loader2, Trash2, TrendingUp, X } from "lucide-react";
import {
  createSymptom,
  deleteSymptom,
  getSymptomCorrelations,
  listSymptoms,
  updateSymptom,
} from "../../lib/api/symptoms";
import {
  groupBySymptom,
  SYMPTOM_PRESETS,
  SYMPTOM_SEVERITIES,
  type SymptomEntry,
  type SymptomSeverity,
} from "../../lib/types/symptom";
import { todayIso, formatDate } from "../../lib/utils";

const SEVERITY_STYLES: Record<SymptomSeverity, string> = {
  mild: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  moderate: "bg-warning/15 text-warning-foreground",
  severe: "bg-danger/10 text-danger",
};

/**
 * Symptom journal with a per-symptom correlation view. Correlations are
 * co-occurrence counts, never causes — the disclaimer ships with the data
 * and stays on screen.
 */
export default function SymptomJournal({ memberId }: { memberId: string }) {
  const {
    data: entries,
    error: listError,
    isLoading,
    mutate,
  } = useSWR<SymptomEntry[]>(
    memberId ? ["symptoms", memberId] : null,
    ([, id]: [string, string]) => listSymptoms(id),
  );
  const [symptom, setSymptom] = useState("");
  const [severity, setSeverity] = useState<SymptomSeverity>("moderate");
  const [startedAt, setStartedAt] = useState(todayIso);
  const [notes, setNotes] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openCorrelation, setOpenCorrelation] = useState<string | null>(null);

  const bySymptom = useMemo(() => groupBySymptom(entries ?? []), [entries]);

  async function run(action: () => Promise<unknown>, fallback: string) {
    setActionError(null);
    setBusy(true);
    try {
      await action();
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  function handleAdd(preset?: string) {
    const key = (preset ?? symptom).trim().toLowerCase();
    if (!key) return;
    void run(async () => {
      await createSymptom(memberId, {
        symptom: key,
        severity,
        started_at: startedAt,
        notes: notes || null,
      });
      setSymptom("");
      setNotes("");
    }, "Could not log the symptom.");
  }

  function handleResolve(entry: SymptomEntry) {
    void run(
      () =>
        updateSymptom(memberId, entry.id, {
          resolved_at: entry.resolved_at ? null : todayIso(),
        }),
      "Could not update the entry.",
    );
  }

  function handleDelete(id: string) {
    void run(() => deleteSymptom(memberId, id), "Could not delete the entry.");
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading journal…
      </div>
    );
  }

  if (listError) {
    return (
      <section aria-label="Symptom journal">
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load the journal.{" "}
          {listError instanceof Error ? listError.message : ""}
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Symptom journal" className="space-y-4">
      <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
        <Activity className="size-5 text-primary" aria-hidden />
        Symptom journal
      </h2>

      {/* Quick log */}
      <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="flex flex-wrap gap-1.5">
          {SYMPTOM_PRESETS.slice(0, 10).map((preset) => (
            <button
              key={preset}
              type="button"
              disabled={busy}
              onClick={() => handleAdd(preset)}
              className="rounded-full border border-border px-2.5 py-1 text-xs capitalize text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              {preset.replace(/_/g, " ")}
            </button>
          ))}
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-4">
          <label className="space-y-1.5 text-sm font-medium">
            Other
            <input
              value={symptom}
              onChange={(e) => setSymptom(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              placeholder="free text…"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Severity
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as SymptomSeverity)}
              aria-label="Severity"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            >
              {SYMPTOM_SEVERITIES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Started
            <input
              type="date"
              value={startedAt}
              onChange={(e) => setStartedAt(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Notes
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="triggers, context…"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
        </div>
        <button
          type="button"
          disabled={busy || !symptom.trim()}
          onClick={() => handleAdd()}
          className="mt-3 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
          Log symptom
        </button>
        {actionError && (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {actionError}
          </p>
        )}
      </div>

      {/* Journal grouped by symptom */}
      {bySymptom.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
          Nothing logged yet — tap a preset above when something hurts.
        </p>
      ) : (
        bySymptom.map(([key, list]) => (
          <div
            key={key}
            className="rounded-xl border border-border bg-card p-4 shadow-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold capitalize">
                {key.replace(/_/g, " ")}{" "}
                <span className="font-normal text-muted-foreground">
                  ({list.length})
                </span>
              </p>
              <button
                type="button"
                aria-expanded={openCorrelation === key}
                onClick={() =>
                  setOpenCorrelation(openCorrelation === key ? null : key)
                }
                className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-muted"
              >
                {openCorrelation === key ? (
                  <>
                    <X className="size-3.5" aria-hidden />
                    Hide pattern
                  </>
                ) : (
                  <>
                    <TrendingUp className="size-3.5" aria-hidden />
                    What's behind it?
                  </>
                )}
              </button>
            </div>
            {openCorrelation === key && (
              <CorrelationView memberId={memberId} symptom={key} />
            )}
            <ul className="mt-3 space-y-1.5">
              {list.map((entry) => (
                <li
                  key={entry.id}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border px-3 py-2"
                >
                  <div className="min-w-0 text-sm">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs font-medium capitalize ${SEVERITY_STYLES[entry.severity]}`}
                    >
                      {entry.severity}
                    </span>{" "}
                    <span className="text-muted-foreground">
                      {formatDate(entry.started_at)}
                      {entry.resolved_at
                        ? ` → resolved ${formatDate(entry.resolved_at)}`
                        : " → ongoing"}
                    </span>
                    {entry.notes && (
                      <p className="truncate text-xs text-muted-foreground">
                        {entry.notes}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      onClick={() => handleResolve(entry)}
                      className="rounded-lg px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      {entry.resolved_at ? "Reopen" : "Resolve"}
                    </button>
                    <button
                      type="button"
                      aria-label="Delete entry"
                      onClick={() => handleDelete(entry.id)}
                      className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger"
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}

function CorrelationView({
  memberId,
  symptom,
}: {
  memberId: string;
  symptom: string;
}) {
  const { data, error, isLoading } = useSWR(
    ["symptom-correlations", memberId, symptom],
    ([, id, s]: [string, string, string]) => getSymptomCorrelations(id, s),
  );
  if (isLoading) {
    return <p className="mt-2 text-xs text-muted-foreground">Crunching…</p>;
  }
  if (error || !data) {
    return (
      <p className="mt-2 rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground">
        Correlation analysis is not available right now.
      </p>
    );
  }

  const rows: [string, typeof data.with_medications][] = [
    ["Active medications around onsets", data.with_medications],
    ["Abnormal labs nearby", data.with_abnormal_labs],
    ["Co-occurring symptoms", data.co_occurring_symptoms],
  ];

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">
        {data.occurrences} occurrence(s), {formatDate(data.first_seen)} →{" "}
        {formatDate(data.last_seen)}
      </p>
      {rows.map(([label, hits]) => (
        <div key={label}>
          <p className="text-xs font-semibold text-muted-foreground">{label}</p>
          {hits.length === 0 ? (
            <p className="text-xs text-muted-foreground/60">Nothing notable</p>
          ) : (
            <ul className="text-xs">
              {hits.slice(0, 5).map((hit) => (
                <li key={hit.name}>
                  {hit.name} — {hit.count}/{hit.of} onsets
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
      <p className="text-xs text-muted-foreground/70">{data.disclaimer}</p>
    </div>
  );
}
