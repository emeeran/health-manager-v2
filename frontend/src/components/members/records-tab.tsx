import { CalendarPlus, Loader2, Paperclip } from "lucide-react";
import { Link } from "react-router-dom";
import BatchUpload from "../records/batch-upload";
import { recordTypeMeta } from "../../lib/record-types";
import type { HealthRecord } from "../../lib/types/record";
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
  return (
    <div className="space-y-6">
      <BatchUpload memberId={memberId} />
      <RecordsTimeline
        records={records}
        isLoading={isLoading}
        memberId={memberId}
        memberName={memberName}
      />
    </div>
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
            ? `Add ${memberName}'s first doctor visit, lab report or prescription.`
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
