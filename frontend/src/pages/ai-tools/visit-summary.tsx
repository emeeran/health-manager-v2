import { AiToolPage } from "../../components/ai-tools/ai-tool-page";
import { InsightTool } from "../../components/ai-tools/insight-tool";
import { listRecords } from "../../lib/api/records";
import type { HealthRecord } from "../../lib/types/record";
import { useEffect, useState } from "react";
import useSWR from "swr";

const selectClass =
  "rounded-lg border border-input bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring";

function visitLabel(record: HealthRecord): string {
  const doctor = record.doctor_name ? ` — ${record.doctor_name}` : "";
  const diagnosis = record.diagnosis ? ` · ${record.diagnosis}` : "";
  return `${record.record_date}${doctor}${diagnosis}`;
}

/**
 * Doctor Visit Summary: pick ONE doctor_visit record, then summarize it.
 * The picker feeds record_id to the visit_summary stream endpoint.
 */
export default function VisitSummaryPage() {
  return (
    <AiToolPage title="Doctor visit summary">
      {(memberId) => <VisitSummaryTool memberId={memberId} />}
    </AiToolPage>
  );
}

function VisitSummaryTool({ memberId }: { memberId: string }) {
  const { data: visits } = useSWR(
    ["records", "doctor_visit", memberId],
    () => listRecords(memberId, { record_type: "doctor_visit", limit: 50 }),
  );
  // Default to the newest visit (listRecords returns newest-first) so the
  // tool is usable immediately; the picker switches the summarized visit.
  const [recordId, setRecordId] = useState("");
  useEffect(() => {
    if (visits?.length) setRecordId((current) => current || visits[0].id);
  }, [visits]);

  if (!visits) {
    return <p className="text-sm text-muted-foreground">Loading visits…</p>;
  }

  if (!visits.length) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
        No doctor visits recorded for this member yet — add one under Records
        first.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        Visit
        <select
          value={recordId}
          onChange={(e) => setRecordId(e.target.value)}
          className={selectClass}
        >
          {visits.map((visit) => (
            <option key={visit.id} value={visit.id}>
              {visitLabel(visit)}
            </option>
          ))}
        </select>
      </label>
      {recordId && (
        <InsightTool
          key={recordId}
          memberId={memberId}
          kind="visit_summary"
          description="Summary of one specific visit — diagnosis, treatment and follow-up"
          recordId={recordId}
        />
      )}
    </div>
  );
}
