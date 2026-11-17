import { ArrowLeft, Loader2, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { CurrentMedicationsPrompt } from "../components/members/current-medications-prompt";
import { ClinicalDataView } from "../components/records/clinical-data-view";
import { ConfidentialityBadge } from "../components/records/confidentiality";
import { RecordAttachments } from "../components/records/record-attachments";
import { TrackPrescriptionMeds } from "../components/records/track-prescription-meds";
import { deleteRecord } from "../lib/api/records";
import { recordTypeMeta } from "../lib/record-types";
import type { HealthRecord } from "../lib/types/record";
import { errorMessage } from "../lib/utils";

export default function RecordDetail() {
  const { memberId = "", recordId = "" } = useParams();
  // Arriving from the wizard with attached documents (?extract=1) kicks off
  // extraction for every attachment automatically.
  const [searchParams, setSearchParams] = useSearchParams();
  const autoExtract = searchParams.get("extract") === "1";
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(false);
  const {
    data: record,
    error,
    isLoading,
    mutate,
  } = useSWR<HealthRecord>(
    memberId && recordId ? `/members/${memberId}/records/${recordId}` : null,
  );

  async function handleDelete() {
    if (!record) return;
    if (!window.confirm("Delete this record? Its attachments go with it."))
      return;
    setDeleting(true);
    setDeleteError(false);
    try {
      await deleteRecord(memberId, recordId);
      await navigate(`/members/${memberId}`);
    } catch {
      setDeleteError(true);
    } finally {
      setDeleting(false);
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl">
        <p
          role="alert"
          className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load this record.{" "}
          {errorMessage(error, "")}
        </p>
      </div>
    );
  }

  if (isLoading || !record) {
    return (
      <div className="mx-auto flex max-w-3xl items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading record…
      </div>
    );
  }

  const { label, icon: TypeIcon } = recordTypeMeta(record.record_type);
  const extractedMedsCount =
    (record.clinical_data?.medications as unknown[] | undefined)?.length ?? 0;
  const hasClinicalData =
    record.clinical_data && Object.keys(record.clinical_data).length > 0;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        to={`/members/${memberId}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Back to member
      </Link>

      {extractedMedsCount > 0 && (
        <>
          <CurrentMedicationsPrompt memberId={memberId} />
          <TrackPrescriptionMeds memberId={memberId} record={record} />
        </>
      )}

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <TypeIcon className="size-5" aria-hidden />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{label}</h1>
              <ConfidentialityBadge level={record.confidentiality_level} />
            </div>
            <p className="text-sm text-muted-foreground">
              {record.record_date}
              {record.record_time ? ` · ${record.record_time.slice(0, 5)}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {deleteError && (
            <span role="alert" className="text-xs text-danger">
              Delete failed
            </span>
          )}
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
          >
            {deleting ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Trash2 className="size-4" aria-hidden />
            )}
            Delete record
          </button>
        </div>
      </div>

      <section
        className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
        aria-label="Record details"
      >
        {/* Declutter: only fields that actually carry data render. */}
        {record.diagnosis && <DetailField label="Diagnosis" value={record.diagnosis} />}
        {record.investigations && (
          <DetailField label="Investigations" value={record.investigations} />
        )}
        {record.doctor_name && <DetailField label="Doctor" value={record.doctor_name} />}
        {record.provider_name && (
          <DetailField label="Provider" value={record.provider_name} />
        )}
        {record.summary && <DetailField label="Summary" value={record.summary} multiline />}
        {record.prescription_text && (
          <DetailField
            label="Prescription"
            value={record.prescription_text}
            multiline
          />
        )}
        {record.tags.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Tags
            </p>
            <ul className="mt-1.5 flex flex-wrap gap-1.5">
              {record.tags.map((tag) => (
                <li
                  key={tag}
                  className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary"
                >
                  {tag}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {hasClinicalData && (
        <section
          aria-label="Extracted clinical data"
          className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
        >
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4 text-primary" aria-hidden />
            Structured data
          </h2>
          <p className="text-xs text-muted-foreground">
            Saved alongside this record from document extraction — feeds trends,
            alerts, and the AI reports.
          </p>
          <ClinicalDataView
            data={record.clinical_data as Record<string, unknown>}
          />
        </section>
      )}

      <RecordAttachments
        record={record}
        memberId={memberId}
        autoExtract={autoExtract}
        onAutoExtractStarted={() => setSearchParams({}, { replace: true })}
        onChanged={() => void mutate()}
      />
    </div>
  );
}

function DetailField({
  label,
  value,
  multiline = false,
}: {
  label: string;
  value: string | null;
  multiline?: boolean;
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      {multiline ? (
        <p className="mt-1 whitespace-pre-wrap text-sm">
          {value || <span className="text-muted-foreground">—</span>}
        </p>
      ) : (
        <p className="mt-1 text-sm">
          {value || <span className="text-muted-foreground">—</span>}
        </p>
      )}
    </div>
  );
}
