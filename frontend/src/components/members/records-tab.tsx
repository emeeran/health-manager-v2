import { CalendarPlus, Loader2, Paperclip } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import BatchUpload from "../records/batch-upload";
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
  const filtered =
    typeFilter === "all"
      ? records
      : records?.filter((r) => r.record_type === typeFilter);

  return (
    <div className="space-y-6">
      <BatchUpload memberId={memberId} />
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
      <RecordsTimeline
        records={filtered}
        isLoading={isLoading}
        memberId={memberId}
        memberName={memberName}
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
}: {
  records?: HealthRecord[];
  isLoading: boolean;
  memberId: string;
  memberName?: string;
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
                <li key={record.id}>
                  <Link
                    to={`/members/${memberId}/records/${record.id}`}
                    className="block rounded-xl border border-border bg-card px-4 py-3 shadow-sm transition-colors hover:border-primary/50"
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
