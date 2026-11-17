import {
  CalendarPlus,
  CheckSquare,
  Loader2,
  Paperclip,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useSWRConfig } from "swr";
import BatchUpload from "../records/batch-upload";
import { deleteRecords } from "../../lib/api/records";
import { recordTypeMeta, RECORD_TYPE_META } from "../../lib/record-types";
import { RECORD_TYPES, type HealthRecord, type RecordType } from "../../lib/types/record";
import { ConfidentialityBadge } from "../records/confidentiality";

interface DateGroup {
  date: string;
  records: HealthRecord[];
}

function groupByDate(records: HealthRecord[]): DateGroup[] {
  const groups: DateGroup[] = [];
  for (const record of records) {
    const last = groups[groups.length - 1];
    if (last && last.date === record.record_date) {
      last.records.push(record);
    } else {
      groups.push({ date: record.record_date, records: [record] });
    }
  }
  return groups;
}

/** Records tab: batch AI extraction + the reverse-chronological timeline. */
export function RecordsTab({
  records,
  isLoading,
  memberId,
  memberName,
}: {
  records?: HealthRecord[];
  isLoading: boolean;
  memberId: string;
  memberName?: string;
}) {
  const [typeFilter, setTypeFilter] = useState<RecordType | "all">("all");
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { mutate } = useSWRConfig();

  const filtered =
    typeFilter === "all"
      ? records
      : records?.filter((r) => r.record_type === typeFilter);

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function exitSelectMode() {
    setSelectMode(false);
    setSelected(new Set());
    setError(null);
  }

  async function handleBulkDelete() {
    if (!records || selected.size === 0) return;
    const message =
      selected.size === 1
        ? "Delete this record? Its attachments go with it."
        : `Delete ${selected.size} records? Their attachments go with them.`;
    if (!window.confirm(message)) return;
    setDeleting(true);
    setError(null);
    try {
      const result = await deleteRecords(memberId, [...selected]);
      // Timeline + count views re-fetch; only this member's records changed.
      await mutate((key) => key === `/members/${memberId}/records`);
      exitSelectMode();
      if (result.not_found.length > 0) {
        setError(
          `${result.deleted} deleted — ${result.not_found.length} were already gone.`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete records.");
    } finally {
      setDeleting(false);
    }
  }

  const hasRecords = !!records && records.length > 0;

  return (
    <div className="space-y-6">
      <BatchUpload memberId={memberId} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        {records && records.length > 0 && (
          <div
            role="group"
            aria-label="Filter by record type"
            className="flex flex-wrap gap-1.5"
          >
            <FilterChip
              active={typeFilter === "all"}
              label="All"
              count={records.length}
              onClick={() => setTypeFilter("all")}
            />
            {RECORD_TYPES.map((type) => {
              const count = records.filter((r) => r.record_type === type).length;
              if (count === 0) return null;
              return (
                <FilterChip
                  key={type}
                  active={typeFilter === type}
                  label={RECORD_TYPE_META[type].label}
                  count={count}
                  onClick={() => setTypeFilter(type)}
                />
              );
            })}
          </div>
        )}
        {hasRecords && (
          <button
            type="button"
            aria-pressed={selectMode}
            onClick={() => (selectMode ? exitSelectMode() : setSelectMode(true))}
            className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {selectMode ? (
              <>
                <X className="size-3.5" aria-hidden /> Cancel
              </>
            ) : (
              <>
                <CheckSquare className="size-3.5" aria-hidden /> Select
              </>
            )}
          </button>
        )}
      </div>
      {selectMode && hasRecords && (
        <div
          role="toolbar"
          aria-label="Bulk actions"
          className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm shadow-sm"
        >
          <button
            type="button"
            onClick={() =>
              setSelected(new Set((filtered ?? []).map((r) => r.id)))
            }
            className="text-xs font-medium text-primary hover:underline"
          >
            Select all{typeFilter !== "all" ? " shown" : ""}
          </button>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Clear
          </button>
          <span className="text-xs text-muted-foreground">
            {selected.size} selected
          </span>
          <button
            type="button"
            disabled={selected.size === 0 || deleting}
            onClick={() => void handleBulkDelete()}
            className="ml-auto flex items-center gap-1.5 rounded-lg bg-danger px-3 py-1.5 text-xs font-medium text-danger-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {deleting ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : (
              <Trash2 className="size-3.5" aria-hidden />
            )}
            Delete selected
          </button>
        </div>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}
      <RecordsTimeline
        records={filtered}
        isLoading={isLoading}
        memberId={memberId}
        memberName={memberName}
        selectMode={selectMode}
        selected={selected}
        onToggle={toggleSelected}
      />
    </div>
  );
}

function FilterChip({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
        active
          ? "border-primary/40 bg-primary/10 text-primary"
          : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      {label} <span className="text-[10px] opacity-70">{count}</span>
    </button>
  );
}

function RecordsTimeline({
  records,
  isLoading,
  memberId,
  memberName,
  selectMode,
  selected,
  onToggle,
}: {
  records?: HealthRecord[];
  isLoading: boolean;
  memberId: string;
  memberName?: string;
  selectMode: boolean;
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading records…
      </div>
    );
  }

  if (!records || records.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border bg-card p-10 text-center">
        <CalendarPlus className="size-8 text-muted-foreground" aria-hidden />
        <p className="text-sm font-medium">No records yet</p>
        <p className="text-sm text-muted-foreground">
          {memberName
            ? `Add ${memberName}'s first document — it gets extracted automatically.`
            : "Add the first record with the button above."}
        </p>
      </div>
    );
  }

  return (
    <section aria-label="Records timeline" className="relative pl-4">
      <div
        aria-hidden
        className="absolute top-2 bottom-2 left-[7px] w-px bg-border"
      />
      <div className="space-y-6">
        {groupByDate(records).map((group) => (
          <div key={group.date}>
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <span
                aria-hidden
                className="absolute left-[4px] size-[7px] rounded-full bg-primary/60"
              />
              {group.date}
            </p>
            <ul className="space-y-2">
              {group.records.map((record) => (
                <li key={record.id} className="flex items-start gap-2">
                  {selectMode && (
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={selected.has(record.id)}
                      aria-label={`Select record from ${record.record_date}`}
                      onClick={() => onToggle(record.id)}
                      className="mt-3 shrink-0 text-muted-foreground transition-colors hover:text-primary"
                    >
                      {selected.has(record.id) ? (
                        <CheckSquare className="size-4 text-primary" aria-hidden />
                      ) : (
                        <Square className="size-4" aria-hidden />
                      )}
                    </button>
                  )}
                  <Link
                    to={`/members/${memberId}/records/${record.id}`}
                    onClick={(e) => {
                      if (selectMode) {
                        e.preventDefault();
                        onToggle(record.id);
                      }
                    }}
                    className={`block flex-1 rounded-xl border bg-card px-4 py-3 shadow-sm transition-colors hover:border-primary/50 ${
                      selected.has(record.id)
                        ? "border-primary/70 bg-primary/5"
                        : "border-border"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {recordTypeIcon(record.record_type)}
                      <span className="text-sm font-medium">
                        {recordTypeMeta(record.record_type).label}
                      </span>
                      <ConfidentialityBadge
                        level={record.confidentiality_level}
                      />
                      {record.record_time && (
                        <span className="text-xs text-muted-foreground">
                          {record.record_time.slice(0, 5)}
                        </span>
                      )}
                      {record.attachments.length > 0 && (
                        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
                          <Paperclip className="size-3.5" aria-hidden />
                          {record.attachments.length}
                        </span>
                      )}
                    </div>
                    {(record.doctor_name || record.summary) && (
                      <div className="mt-1.5 space-y-0.5 text-sm">
                        {record.doctor_name && (
                          <p className="text-muted-foreground">
                            {record.doctor_name}
                          </p>
                        )}
                        {record.summary && (
                          <p className="line-clamp-2 text-muted-foreground">
                            {record.summary}
                          </p>
                        )}
                      </div>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

function recordTypeIcon(recordType: string) {
  const { icon: Icon } = recordTypeMeta(recordType);
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
      <Icon className="size-4" aria-hidden />
    </span>
  );
}
