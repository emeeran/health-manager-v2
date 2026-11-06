import {
  Activity,
  ArrowLeft,
  CalendarPlus,
  FileText,
  Loader2,
  NotebookPen,
  Pencil,
  Phone,
  Share2,
  EllipsisVertical,
  ShieldCheck,
  TrendingUp,
  User,
  UserRound,
  X,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import useSWR from "swr";
import { OverviewTab } from "../components/members/overview-tab";
import { RecordsTab } from "../components/members/records-tab";
import { JournalTab } from "../components/members/journal-tab";
import { SafetyTab } from "../components/members/safety-tab";
import { ConditionsTab } from "../components/members/conditions-tab";
import { useEscClose } from "../hooks/use-esc-close";
import TrendsSection from "../components/vitals/trends-section";
import LabsSection from "../components/labs/labs-section";
import { TabErrorBoundary } from "../components/shared/tab-error-boundary";
import RecordWizard from "../components/records/record-wizard";
import { ShareDialog } from "../components/members/share-dialog";
import { MemberEditDialog } from "../components/members/member-edit-dialog";
import { createRecord } from "../lib/api/records";
import { lastDoctorName } from "../lib/wizard-state";
import { recordTypeMeta } from "../lib/record-types";
import {
  RECORD_TYPES,
  type HealthRecord,
  type RecordType,
} from "../lib/types/record";
import type { Member } from "../lib/types/member";
import { INPUT_CLASS, todayIso } from "../lib/utils";

type TabId =
  "overview" | "records" | "trends" | "journal" | "safety" | "conditions";

const TABS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "overview", label: "Overview", icon: User },
  { id: "records", label: "Records", icon: FileText },
  { id: "trends", label: "Trends", icon: TrendingUp },
  { id: "journal", label: "Journal", icon: NotebookPen },
  { id: "safety", label: "Safety", icon: ShieldCheck },
  { id: "conditions", label: "Conditions", icon: Activity },
];

const VALID_TABS = new Set<string>(TABS.map((tab) => tab.id));

export default function MemberDetail() {
  const { memberId = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab") ?? "overview";
  const activeTab: TabId = VALID_TABS.has(rawTab)
    ? (rawTab as TabId)
    : "overview";

  function handleTabChange(tab: TabId) {
    setSearchParams(tab === "overview" ? {} : { tab }, { replace: true });
  }

  const [formOpen, setFormOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const {
    data: member,
    error: memberError,
    isLoading: memberLoading,
    mutate: mutateMember,
  } = useSWR<Member>(memberId ? `/members/${memberId}` : null);
  const {
    data: records,
    error: recordsError,
    isLoading: recordsLoading,
  } = useSWR<HealthRecord[]>(memberId ? `/members/${memberId}/records` : null);

  const panels = useMemo(
    () => ({
      overview: (
        <TabErrorBoundary label="Overview">
          <OverviewTab member={member} />
        </TabErrorBoundary>
      ),
      records: (
        <TabErrorBoundary label="Records">
          <RecordsTab
            records={records}
            isLoading={recordsLoading}
            memberId={memberId}
            memberName={member?.name}
          />
        </TabErrorBoundary>
      ),
      trends: (
        <TabErrorBoundary label="Trends">
          <div className="space-y-6">
            <TrendsSection memberId={memberId} />
            <LabsSection memberId={memberId} />
          </div>
        </TabErrorBoundary>
      ),
      journal: (
        <TabErrorBoundary label="Journal">
          <JournalTab memberId={memberId} />
        </TabErrorBoundary>
      ),
      safety: (
        <TabErrorBoundary label="Safety">
          <SafetyTab memberId={memberId} />
        </TabErrorBoundary>
      ),
      conditions: (
        <TabErrorBoundary label="Conditions">
          <ConditionsTab memberId={memberId} />
        </TabErrorBoundary>
      ),
    }),
    [member, records, recordsLoading, memberId],
  );

  const loadError = memberError ?? recordsError;
  if (loadError) {
    return (
      <div className="mx-auto max-w-3xl">
        <p
          role="alert"
          className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load this member.{" "}
          {loadError instanceof Error ? loadError.message : ""}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        to="/members"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        All members
      </Link>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary/15 text-lg font-semibold text-primary">
            {(member?.name ?? "…").charAt(0).toUpperCase()}
          </span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {memberLoading ? "Loading…" : (member?.name ?? "Member")}
            </h1>
            <div className="mt-0.5 flex items-center gap-2 text-sm text-muted-foreground">
              {member && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium capitalize text-primary">
                  {member.relationship}
                </span>
              )}
              {member?.birth_date && (
                <span className="flex items-center gap-1 text-xs">
                  <UserRound className="size-3.5" aria-hidden />
                  {member.birth_date}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <OverflowMenu
            items={[
              {
                label: "Edit member",
                icon: <Pencil className="size-4" aria-hidden />,
                onSelect: () => setEditOpen(true),
              },
              {
                label: "ICE card",
                icon: <Phone className="size-4" aria-hidden />,
                onSelect: () => navigate(`/members/${memberId}/emergency`),
              },
              {
                label: "Share",
                icon: <Share2 className="size-4" aria-hidden />,
                onSelect: () => setShareOpen(true),
              },
            ]}
          />
          <button
            type="button"
            onClick={() => setFormOpen(true)}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <CalendarPlus className="size-4" aria-hidden />
            New record
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div
        role="tablist"
        aria-label="Member sections"
        className="flex gap-1 overflow-x-auto border-b border-border"
      >
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`member-tab-${id}`}
            aria-selected={activeTab === id}
            aria-controls={`member-panel-${id}`}
            onClick={() => handleTabChange(id)}
            className={
              "inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors " +
              (activeTab === id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground")
            }
          >
            <Icon className="size-3.5" aria-hidden />
            {label}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`member-panel-${activeTab}`}
        aria-labelledby={`member-tab-${activeTab}`}
      >
        {panels[activeTab]}
      </div>

      {formOpen && (
        <RecordCreateModal
          memberId={memberId}
          onClose={() => setFormOpen(false)}
          onCreated={(record, attachedFiles) => {
            setFormOpen(false);
            // Attached Rx/lab reports go straight into auto-extraction.
            void navigate(
              `/members/${memberId}/records/${record.id}${(attachedFiles ?? 0) > 0 ? "?extract=1" : ""}`,
            );
          }}
        />
      )}

      {shareOpen && member && (
        <ShareDialog
          memberId={memberId}
          memberName={member.name}
          onClose={() => setShareOpen(false)}
        />
      )}

      {editOpen && member && (
        <MemberEditDialog
          member={member}
          onClose={() => setEditOpen(false)}
          onSaved={(saved) => {
            void mutateMember(saved, { revalidate: false });
            setEditOpen(false);
          }}
        />
      )}
    </div>
  );
}

/**
 * Record creation modal: the multi-step wizard is the default path; the
 * classic single form stays available as a toggle for quick entries.
 */
function RecordCreateModal({
  memberId,
  onClose,
  onCreated,
}: {
  memberId: string;
  onClose: () => void;
  onCreated: (record: HealthRecord, attachedFiles?: number) => void;
}) {
  const [mode, setMode] = useState<"wizard" | "classic">("wizard");

  // Escape closes the modal (routed through the global overlay stack).
  useEscClose(true, onClose);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8"
      role="dialog"
      aria-modal="true"
      aria-label="New record"
    >
      <div className="w-full max-w-2xl space-y-3">
        <div className="flex items-center justify-between">
          <div
            role="group"
            aria-label="Form mode"
            className="flex rounded-lg border border-border bg-card p-0.5"
          >
            <button
              type="button"
              aria-pressed={mode === "wizard"}
              onClick={() => setMode("wizard")}
              className={
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors " +
                (mode === "wizard"
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground")
              }
            >
              Guided wizard
            </button>
            <button
              type="button"
              aria-pressed={mode === "classic"}
              onClick={() => setMode("classic")}
              className={
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors " +
                (mode === "classic"
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground")
              }
            >
              Classic form
            </button>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="size-5" aria-hidden />
          </button>
        </div>

        {mode === "wizard" ? (
          <RecordWizard memberId={memberId} onCreated={onCreated} />
        ) : (
          <CreateRecordForm memberId={memberId} onCreated={onCreated} />
        )}
      </div>
    </div>
  );
}

function CreateRecordForm({
  memberId,
  onCreated,
}: {
  memberId: string;
  onCreated: (record: HealthRecord) => void;
}) {
  const [recordType, setRecordType] = useState<RecordType>("doctor_visit");
  const [recordDate, setRecordDate] = useState(todayIso);
  const [diagnosis, setDiagnosis] = useState("");
  const [summary, setSummary] = useState("");
  const [doctorName, setDoctorName] = useState(lastDoctorName);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const record = await createRecord(memberId, {
        record_type: recordType,
        record_date: recordDate,
        ...(diagnosis ? { diagnosis } : {}),
        ...(summary ? { summary } : {}),
        ...(doctorName.trim() ? { doctor_name: doctorName.trim() } : {}),
      });
      onCreated(record);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create record.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border bg-card p-5 shadow-sm"
      aria-label="New record"
    >
      <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
        <CalendarPlus className="size-4" aria-hidden />
        New record
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1.5 text-sm font-medium">
          Type
          <select
            value={recordType}
            onChange={(e) => setRecordType(e.target.value as RecordType)}
            className={INPUT_CLASS}
          >
            {RECORD_TYPES.map((value) => (
              <option key={value} value={value}>
                {recordTypeMeta(value).label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Date
          <input
            type="date"
            required
            value={recordDate}
            onChange={(e) => setRecordDate(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Doctor name
          <input
            placeholder="Optional"
            value={doctorName}
            onChange={(e) => setDoctorName(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
          Diagnosis
          <input
            placeholder="Optional"
            value={diagnosis}
            onChange={(e) => setDiagnosis(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
          Summary
          <textarea
            rows={3}
            placeholder="Optional"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
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
        disabled={submitting}
        className="mt-4 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
      >
        {submitting && <Loader2 className="size-4 animate-spin" aria-hidden />}
        Create record
      </button>
    </form>
  );
}

interface OverflowItem {
  label: string;
  icon: React.ReactNode;
  onSelect: () => void;
}

/** Secondary actions tucked behind a kebab button, keeping the header to
 * primary action + overflow. */
function OverflowMenu({ items }: { items: OverflowItem[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="More actions"
        onClick={() => setOpen((value) => !value)}
        className="rounded-lg border border-border p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <EllipsisVertical className="size-4" aria-hidden />
      </button>
      {open && (
        <>
          {/* Click-away catcher */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div
            role="menu"
            aria-label="Member actions"
            className="absolute right-0 top-full z-50 mt-1 w-44 rounded-lg border border-border bg-card py-1 shadow-lg"
          >
            {items.map((item) => (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-sm transition-colors hover:bg-muted"
              >
                <span className="text-muted-foreground">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
