import { useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  FileWarning,
  Loader2,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { confirmSmartEntry, parseSmartEntry } from "../../lib/api/smart-entry";
import {
  CONFIDENCE_STYLES,
  type SmartEntryConfirmInput,
  type SmartEntryDraft,
} from "../../lib/types/smart-entry";
import { recordTypeMeta } from "../../lib/record-types";
import type { RecordType } from "../../lib/types/record";
import { VoiceMemoButton } from "./voice-memo-button";
import { INPUT_CLASS } from "../../lib/utils";

interface DraftState {
  parsed: SmartEntryDraft;
  saving: boolean;
  saved: boolean;
  savedRecordId: string | null;
  error: string | null;
}

/**
 * Smart entry bar: describe a visit in plain words → AI parses a draft →
 * confirm-to-save (POST /smart-entry/confirm). Nothing is written until
 * "Save draft" is pressed.
 */
export function SmartEntryBar({ memberId }: { memberId?: string }) {
  const [text, setText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<DraftState[]>([]);

  async function handleParse() {
    const value = text.trim();
    if (!value) return;
    setParsing(true);
    setParseError(null);
    try {
      const parsed = await parseSmartEntry(value);
      setDrafts((prev) => [
        {
          parsed,
          saving: false,
          saved: false,
          savedRecordId: null,
          error: null,
        },
        ...prev,
      ]);
      setText("");
    } catch (err) {
      setParseError(
        err instanceof Error ? err.message : "Could not parse the text.",
      );
    } finally {
      setParsing(false);
    }
  }

  function patchDraft(index: number, patch: Partial<DraftState>) {
    setDrafts((prev) =>
      prev.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    );
  }

  return (
    <section aria-label="Smart entry" className="space-y-3">
      <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Wand2 className="size-4" aria-hidden />
          </span>
          <p className="min-w-0 flex-1 text-sm font-semibold">
            Smart entry
            <span className="ml-2 font-normal text-muted-foreground">
              describe it in one line, AI fills the rest
            </span>
          </p>
        </div>
        <textarea
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void handleParse();
            }
          }}
          placeholder='e.g. "Dad saw Dr. Wang today, diagnosed high blood pressure, prescribed amlodipine 5mg once daily"'
          aria-label="Describe a health event"
          className={`mt-3 ${INPUT_CLASS}`}
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            type="button"
            onClick={() => void handleParse()}
            disabled={parsing || !text.trim()}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {parsing ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Sparkles className="size-4" aria-hidden />
            )}
            Parse draft
          </button>
          {/* Voice dictation needs a member to scope the transcription to;
              the /ai-tools/smart-entry page provides one, the home bar does
              not (the member is parsed out of the text itself). */}
          {memberId && (
            <VoiceMemoButton
              memberId={memberId}
              onTranscript={(transcript) =>
                setText((prev) => (prev ? `${prev} ${transcript}` : transcript))
              }
            />
          )}
        </div>
        {parseError && (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {parseError}
          </p>
        )}
      </div>

      {drafts.map((draft, index) => (
        <DraftCard
          key={index}
          draft={draft}
          onDismiss={() =>
            setDrafts((prev) => prev.filter((_, i) => i !== index))
          }
          onPatch={(patch) => patchDraft(index, patch)}
        />
      ))}
    </section>
  );
}

function DraftCard({
  draft,
  onDismiss,
  onPatch,
}: {
  draft: DraftState;
  onDismiss: () => void;
  onPatch: (patch: Partial<DraftState>) => void;
}) {
  const parsed = draft.parsed;
  const recordType = (parsed.record_type as RecordType) || "other";

  async function handleSave() {
    if (!parsed.member?.id) {
      onPatch({ error: "No member matched — mention a name and parse again." });
      return;
    }
    onPatch({ saving: true, error: null });
    try {
      const input: SmartEntryConfirmInput = {
        member_id: parsed.member.id,
        record_type: parsed.record_type ?? undefined,
        record_date: parsed.record_date ?? undefined,
        diagnosis: parsed.diagnosis ?? undefined,
        summary: parsed.summary ?? undefined,
        provider_name: parsed.provider_name ?? undefined,
        medications: parsed.medications,
        labs: parsed.labs,
        vitals: parsed.vitals,
      };
      const result = await confirmSmartEntry(input);
      onPatch({ saving: false, saved: true, savedRecordId: result.record_id });
    } catch (err) {
      onPatch({
        saving: false,
        error: err instanceof Error ? err.message : "Could not save the draft.",
      });
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {recordTypeMeta(recordType).label} draft
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
                CONFIDENCE_STYLES[parsed.confidence ?? "medium"]
              }`}
            >
              {parsed.confidence ?? "medium"} confidence
            </span>
            {parsed.member && (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {parsed.member.name}
              </span>
            )}
          </p>
          {parsed.record_date && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {parsed.record_date}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {draft.saved ? (
            draft.savedRecordId && parsed.member?.id ? (
              <Link
                to={`/members/${parsed.member.id}/records/${draft.savedRecordId}`}
                className="flex items-center gap-1 text-xs font-medium text-primary hover:underline"
              >
                <CheckCircle2 className="size-4" aria-hidden />
                View record
              </Link>
            ) : (
              <span className="flex items-center gap-1 text-xs font-medium text-primary">
                <CheckCircle2 className="size-4" aria-hidden />
                Saved
              </span>
            )
          ) : (
            <button
              type="button"
              disabled={draft.saving}
              onClick={() => void handleSave()}
              className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {draft.saving ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
              ) : (
                <CheckCircle2 className="size-3.5" aria-hidden />
              )}
              Save draft
            </button>
          )}
          <button
            type="button"
            aria-label="Discard draft"
            onClick={onDismiss}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Trash2 className="size-4" aria-hidden />
          </button>
        </div>
      </div>

      {draft.error && (
        <p
          role="alert"
          className="mt-2 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {draft.error}
        </p>
      )}

      {(parsed.preview_fields?.length ?? 0) > 0 ? (
        <dl className="mt-2 space-y-1">
          {parsed.preview_fields!.map((field) => (
            <div key={field.label} className="flex gap-2 text-sm">
              <dt className="w-32 shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {field.label}
              </dt>
              <dd className="min-w-0 flex-1">{field.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        parsed.diagnosis && (
          <p className="mt-2 text-sm text-muted-foreground">
            {parsed.diagnosis}
          </p>
        )
      )}

      <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
        <FileWarning className="size-3" aria-hidden />
        AI draft — please verify fields before saving.
      </p>
    </div>
  );
}
