import { FlaskConical, Loader2, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { createLab } from "../../lib/api/labs";
import {
  computeFlag,
  labReferenceText,
  parseRefValue,
  type Lab,
  type LabFlag,
} from "../../lib/types/lab";
import { INPUT_CLASS, todayIso } from "../../lib/utils";

/** Server flag wins; otherwise derive it from the numeric value vs range. */
function resolveFlag(lab: Lab): LabFlag | null {
  if (lab.flag === "low" || lab.flag === "normal" || lab.flag === "high") {
    return lab.flag;
  }
  return computeFlag(lab.value_num, lab.ref_low_num, lab.ref_high_num);
}

const FLAG_STYLES: Record<LabFlag, string> = {
  low: "bg-warning/15 text-warning-foreground border-warning/40",
  high: "bg-danger/10 text-danger border-danger/40",
  normal: "bg-primary/10 text-primary border-primary/40",
};

function FlagChip({ flag }: { flag: LabFlag | null }) {
  if (!flag) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${FLAG_STYLES[flag]}`}
    >
      {flag}
    </span>
  );
}

export default function LabsSection({ memberId }: { memberId: string }) {
  const {
    data: labs,
    error,
    isLoading,
    mutate,
  } = useSWR<Lab[]>(memberId ? `/members/${memberId}/labs` : null);

  return (
    <section aria-label="Lab results" className="space-y-4">
      <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
        <FlaskConical className="size-5 text-primary" aria-hidden />
        Labs
      </h2>

      <AddLabForm
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
          Could not load labs. {error instanceof Error ? error.message : ""}
        </p>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading labs…
        </div>
      ) : !labs || labs.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          No lab results yet. Add one above or extract them from an uploaded lab
          report.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Test
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Result
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Units
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Reference
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Flag
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Date
                </th>
              </tr>
            </thead>
            <tbody>
              {labs.map((lab) => (
                <tr
                  key={lab.id}
                  className="border-b border-border/60 last:border-0"
                >
                  <td className="px-4 py-2.5 font-medium">{lab.test_name}</td>
                  <td className="px-4 py-2.5">
                    {lab.value_num !== null && lab.value_num !== undefined
                      ? lab.value_num
                      : (lab.result ?? "—")}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {lab.units ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {labReferenceText(lab)}
                  </td>
                  <td className="px-4 py-2.5">
                    <FlagChip flag={resolveFlag(lab)} />
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {lab.record_date ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function AddLabForm({
  memberId,
  onCreated,
}: {
  memberId: string;
  onCreated: () => void;
}) {
  const [testName, setTestName] = useState("");
  const [result, setResult] = useState("");
  const [units, setUnits] = useState("");
  const [refValue, setRefValue] = useState("");
  const [valueNum, setValueNum] = useState("");
  const [recordDate, setRecordDate] = useState(todayIso);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const parsedValue = valueNum ? Number(valueNum) : undefined;
    if (valueNum && !Number.isFinite(parsedValue)) {
      setError("Value must be numeric.");
      return;
    }
    setSubmitting(true);
    try {
      // Compute the flag client-side when a numeric value and a parseable
      // reference range are both given; the server still validates/overrides.
      let flag: LabFlag | undefined;
      const bounds = refValue ? parseRefValue(refValue) : null;
      if (parsedValue !== undefined && bounds) {
        flag = computeFlag(parsedValue, bounds.low, bounds.high) ?? undefined;
      }
      await createLab(memberId, {
        test_name: testName,
        ...(result ? { result } : {}),
        ...(units ? { units } : {}),
        ...(refValue ? { ref_value: refValue } : {}),
        ...(parsedValue !== undefined ? { value_num: parsedValue } : {}),
        ...(flag ? { flag } : {}),
        ...(recordDate ? { record_date: recordDate } : {}),
      });
      setTestName("");
      setResult("");
      setUnits("");
      setRefValue("");
      setValueNum("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add lab.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border bg-card p-4 shadow-sm"
      aria-label="Add lab result"
    >
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Plus className="size-4 text-primary" aria-hidden />
        Add lab result
      </h3>
      <div className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <label className="space-y-1.5 text-sm font-medium lg:col-span-2">
          Test
          <input
            required
            placeholder="e.g. HbA1c"
            value={testName}
            onChange={(e) => setTestName(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Result
          <input
            placeholder="e.g. 6.8"
            value={result}
            onChange={(e) => setResult(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Units
          <input
            placeholder="e.g. %"
            value={units}
            onChange={(e) => setUnits(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Reference
          <input
            placeholder="e.g. 4.0-5.6"
            value={refValue}
            onChange={(e) => setRefValue(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Date
          <input
            type="date"
            value={recordDate}
            onChange={(e) => setRecordDate(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="space-y-1.5 text-sm font-medium">
          Numeric value
          <input
            type="number"
            inputMode="decimal"
            step="any"
            placeholder="For flag detection"
            value={valueNum}
            onChange={(e) => setValueNum(e.target.value)}
            className={`${INPUT_CLASS} w-40`}
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {submitting && (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          )}
          Add lab
        </button>
      </div>
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
