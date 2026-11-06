import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Loader2,
  Merge,
  RefreshCw,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";
import useSWR from "swr";
import { mergeRecord, scanRecordDuplicates } from "../lib/api/hygiene";
import { listMembers } from "../lib/api/members";
import { listRecords } from "../lib/api/records";
import { recordTypeMeta } from "../lib/record-types";
import {
  mergeDirection,
  reasonLabel,
  type DuplicatePair,
} from "../lib/types/hygiene";
import type { DedupResponse } from "../lib/types/hygiene";
import type { HealthRecord } from "../lib/types/record";
import type { Member } from "../lib/types/member";

/**
 * Data hygiene: scan each member's records for duplicate pairs, then merge
 * with a preview → confirm → result flow. The recommended primary is
 * preselected; merging soft-deletes the loser (`merged_into_id` points at
 * the keeper).
 */
export default function DataHygiene() {
  const {
    data: members,
    isLoading: membersLoading,
    error,
  } = useSWR<Member[]>("/members", listMembers);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Database className="size-6 text-primary" aria-hidden />
          Data hygiene
        </h1>
        <p className="text-sm text-muted-foreground">
          Scan records for likely duplicates and merge them. The recommended
          keeper is preselected; attachments are preserved on merge.
        </p>
      </header>

      {membersLoading ? (
        <div className="flex items-center justify-center gap-2 p-12 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading members…
        </div>
      ) : error ? (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load members. {error instanceof Error ? error.message : ""}
        </p>
      ) : (members ?? []).length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
          No members to scan yet.
        </p>
      ) : (
        (members ?? []).map((member) => (
          <MemberScanSection key={member.id} member={member} />
        ))
      )}
    </div>
  );
}

function MemberScanSection({ member }: { member: Member }) {
  const {
    data,
    error: scanError,
    isLoading,
    mutate,
  } = useSWR<DedupResponse>(
    ["record-duplicates", member.id],
    ([, memberId]: [string, string]) => scanRecordDuplicates(memberId),
  );
  const { data: records } = useSWR<HealthRecord[]>(
    ["all-records", member.id],
    ([, memberId]: [string, string]) => listRecords(memberId, { limit: 100 }),
  );
  const [rescanning, setRescanning] = useState(false);

  const recordById = useMemo(() => {
    const map = new Map<string, HealthRecord>();
    for (const record of records ?? []) map.set(record.id, record);
    return map;
  }, [records]);

  const pairs = data?.pairs ?? [];

  async function rescan() {
    setRescanning(true);
    try {
      await mutate();
    } finally {
      setRescanning(false);
    }
  }

  return (
    <section
      aria-label={`Duplicates for ${member.name}`}
      className="space-y-3 rounded-xl border border-border bg-card p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <span className="flex size-7 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
            {member.name.charAt(0).toUpperCase()}
          </span>
          {member.name}
          {pairs.length > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning-foreground">
              <AlertTriangle className="size-3" aria-hidden />
              {pairs.length} pair{pairs.length !== 1 ? "s" : ""}
            </span>
          )}
        </h2>
        <button
          type="button"
          onClick={() => void rescan()}
          disabled={isLoading || rescanning}
          className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
        >
          {isLoading || rescanning ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <RefreshCw className="size-3.5" aria-hidden />
          )}
          Rescan
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Scanning records…
        </div>
      ) : scanError ? (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not scan duplicates.{" "}
          {scanError instanceof Error ? scanError.message : ""}
        </p>
      ) : pairs.length === 0 ? (
        <p className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-emerald-500" aria-hidden />
          No duplicate pairs found
          {data?.total_records_scanned
            ? ` across ${data.total_records_scanned} records.`
            : "."}
        </p>
      ) : (
        <ul className="space-y-3">
          {pairs.map((pair) => (
            <li key={`${pair.primary_id}-${pair.duplicate_id}`}>
              <DuplicatePairCard
                memberId={member.id}
                pair={pair}
                recordById={recordById}
                onMerged={() => void mutate()}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DuplicatePairCard({
  memberId,
  pair,
  recordById,
  onMerged,
}: {
  memberId: string;
  pair: DuplicatePair;
  recordById: Map<string, HealthRecord>;
  onMerged: () => void;
}) {
  const [keeperId, setKeeperId] = useState(pair.primary_id);
  const [stage, setStage] = useState<"preview" | "confirm" | "success">(
    "preview",
  );
  const [merging, setMerging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const direction = mergeDirection(pair, keeperId);

  async function handleMerge() {
    if (!direction) return;
    setMerging(true);
    setError(null);
    try {
      await mergeRecord(memberId, direction.duplicateId, direction.primaryId);
      setStage("success");
      onMerged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed.");
    } finally {
      setMerging(false);
    }
  }

  if (stage === "success") {
    return (
      <div
        role="status"
        className="flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-600 dark:text-emerald-400"
      >
        <CheckCircle2 className="size-4" aria-hidden />
        Merged{" "}
        {recordTypeMeta(
          recordById.get(direction?.duplicateId ?? "")?.record_type ?? "",
        ).label.toLowerCase()}{" "}
        into the keeper.
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-warning/40 bg-warning/5 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-medium text-warning-foreground">
          <AlertTriangle className="size-4" aria-hidden />
          Possible duplicates
          <span className="text-xs font-normal text-muted-foreground">
            score {pair.score}
            {pair.reason && ` · ${reasonLabel(pair.reason)}`}
          </span>
        </p>
        {stage === "confirm" && (
          <button
            type="button"
            onClick={() => setStage("preview")}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Cancel merge"
          >
            <X className="size-4" aria-hidden />
          </button>
        )}
      </div>

      <ul className="space-y-1.5">
        {[pair.primary_id, pair.duplicate_id].map((recordId) => {
          const record = recordById.get(recordId);
          const isKeeper = recordId === keeperId;
          const typeLabel = record
            ? recordTypeMeta(record.record_type).label
            : "Record";
          return (
            <li key={recordId}>
              <label
                className={`flex cursor-pointer items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                  isKeeper
                    ? "border-primary/60 bg-primary/5"
                    : "border-border bg-card hover:border-primary/40"
                }`}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <input
                    type="radio"
                    name={`keeper-${pair.primary_id}-${pair.duplicate_id}`}
                    checked={isKeeper}
                    onChange={() => setKeeperId(recordId)}
                    aria-label={`Keep ${typeLabel} from ${record?.record_date ?? recordId}`}
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {typeLabel}
                      {isKeeper && (
                        <span className="ml-1.5 text-xs font-normal text-primary">
                          keeper
                        </span>
                      )}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {record
                        ? [
                            record.record_date,
                            record.diagnosis,
                            record.provider_name,
                            record.attachments.length > 0
                              ? `${record.attachments.length} attachment${record.attachments.length !== 1 ? "s" : ""}`
                              : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")
                        : recordId}
                    </span>
                  </span>
                </span>
                {record && (
                  <Link
                    to={`/members/${memberId}/records/${record.id}`}
                    className="shrink-0 text-xs font-medium text-primary hover:underline"
                  >
                    View
                  </Link>
                )}
              </label>
            </li>
          );
        })}
      </ul>

      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}

      {stage === "preview" ? (
        <button
          type="button"
          disabled={!direction}
          onClick={() => setStage("confirm")}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
        >
          <Merge className="size-3.5" aria-hidden />
          Preview merge (2 → 1)
        </button>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-muted-foreground">
            Keep the selected record and merge the other into it? The merged
            record will be hidden from the timeline.
          </p>
          <button
            type="button"
            disabled={merging || !direction}
            onClick={() => void handleMerge()}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {merging ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : (
              <CheckCircle2 className="size-3.5" aria-hidden />
            )}
            Confirm merge
          </button>
        </div>
      )}
    </div>
  );
}
