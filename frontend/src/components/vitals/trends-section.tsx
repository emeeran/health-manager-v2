import { Activity, Loader2, Plus } from "lucide-react";
import { lazy, Suspense, useState, type FormEvent } from "react";
import useSWR, { useSWRConfig } from "swr";
import { createVital, listVitals } from "../../lib/api/vitals";
import type { ReferenceRanges } from "../../lib/types/reference";
import {
  GLUCOSE_CONTEXTS,
  GLUCOSE_CONTEXT_LABELS,
  type GlucoseContext,
  sortByMeasuredDesc,
  VITAL_TYPE_META,
  VITAL_UNITS,
  VITAL_TYPES,
  type Vital,
  type VitalType,
} from "../../lib/types/vital";
import { INPUT_CLASS } from "../../lib/utils";

const VitalsCharts = lazy(() => import("./vitals-charts"));

const RANGES = [
  { key: "7D", days: 7 },
  { key: "30D", days: 30 },
  { key: "90D", days: 90 },
  { key: "1Y", days: 365 },
] as const;

type RangeKey = (typeof RANGES)[number]["key"];

const TILE_TYPES = [
  "blood_pressure",
  "blood_glucose",
  "weight",
  "heart_rate",
  "spo2",
  "hba1c",
] as const satisfies readonly VitalType[];

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE_FORMAT.format(date);
}

function nowLocalInput(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `T${pad(now.getHours())}:${pad(now.getMinutes())}`
  );
}

export default function TrendsSection({ memberId }: { memberId: string }) {
  const [range, setRange] = useState<RangeKey>("30D");
  const { mutate } = useSWRConfig();

  const { data: vitals, isLoading } = useSWR<Vital[]>(
    memberId ? ["vitals", memberId, range] : null,
    ([, id, r]: [string, string, RangeKey]) =>
      listVitals(id, { since: sinceFor(r) }),
    { keepPreviousData: true },
  );
  const { data: latest } = useSWR<Vital[]>(
    memberId ? ["vitals", memberId, "latest"] : null,
    ([, id]: [string, string]) => listVitals(id),
  );
  const { data: ranges } = useSWR<ReferenceRanges>("/reference-ranges");

  async function handleLogged(): Promise<void> {
    await mutate(
      (key) => Array.isArray(key) && key[0] === "vitals" && key[1] === memberId,
    );
  }

  return (
    <section aria-label="Vitals trends" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Activity className="size-5 text-primary" aria-hidden />
          Trends
        </h2>
        <div
          role="group"
          aria-label="Time range"
          className="flex rounded-lg border border-border bg-card p-0.5"
        >
          {RANGES.map((option) => (
            <button
              key={option.key}
              type="button"
              aria-pressed={range === option.key}
              onClick={() => setRange(option.key)}
              className={
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors " +
                (range === option.key
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground")
              }
            >
              {option.key}
            </button>
          ))}
        </div>
      </div>

      <LatestTiles vitals={latest} />
      <LogReadingForm
        memberId={memberId}
        onLogged={() => void handleLogged()}
      />

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading readings…
        </div>
      ) : vitals && vitals.length > 0 ? (
        <Suspense
          fallback={
            <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Loading charts…
            </div>
          }
        >
          <VitalsCharts vitals={vitals} ranges={ranges} />
        </Suspense>
      ) : (
        <p className="rounded-xl border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          No readings in the selected range. Log one below or above.
        </p>
      )}
    </section>
  );
}

function sinceFor(range: RangeKey): string {
  const days = RANGES.find((option) => option.key === range)?.days ?? 30;
  return new Date(Date.now() - days * 86_400_000).toISOString();
}

const TILE_META: Record<(typeof TILE_TYPES)[number], { label: string }> = {
  blood_pressure: { label: "Blood pressure" },
  blood_glucose: { label: "Glucose" },
  weight: { label: "Weight" },
  heart_rate: { label: "Heart rate" },
  spo2: { label: "SpO2" },
  hba1c: { label: "HbA1c" },
};

function formatTileValue(vital: Vital): string {
  switch (vital.vital_type) {
    case "blood_pressure":
      return `${vital.value_num}/${vital.value_secondary ?? "–"} ${
        vital.unit ?? "mmHg"
      }`;
    case "blood_glucose":
      return `${vital.value_num} ${vital.unit ?? "mg/dL"}`;
    default:
      return `${vital.value_num}${vital.unit ? ` ${vital.unit}` : ""}`;
  }
}

function LatestTiles({ vitals }: { vitals?: Vital[] }) {
  if (!vitals || vitals.length === 0) return null;
  const byType = new Map<VitalType, Vital>();
  for (const vital of sortByMeasuredDesc(vitals)) {
    if (!byType.has(vital.vital_type)) byType.set(vital.vital_type, vital);
  }

  const tiles = TILE_TYPES.flatMap((type) => {
    const vital = byType.get(type);
    return vital ? [{ type, vital }] : [];
  });
  if (tiles.length === 0) return null;

  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {tiles.map(({ type, vital }) => (
        <li
          key={type}
          className="rounded-xl border border-border bg-card px-3 py-2.5 shadow-sm"
        >
          <p className="text-xs font-medium text-muted-foreground">
            {TILE_META[type].label}
          </p>
          <p className="mt-0.5 truncate text-lg font-semibold tracking-tight">
            {formatTileValue(vital)}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {vital.vital_type === "blood_glucose" && vital.glucose_context
              ? `${GLUCOSE_CONTEXT_LABELS[vital.glucose_context]} · `
              : ""}
            {formatDate(vital.measured_at)}
          </p>
        </li>
      ))}
    </ul>
  );
}

function LogReadingForm({
  memberId,
  onLogged,
}: {
  memberId: string;
  onLogged: () => void;
}) {
  const [vitalType, setVitalType] = useState<VitalType>("blood_pressure");
  const [value, setValue] = useState("");
  const [secondary, setSecondary] = useState("");
  const [glucoseContext, setGlucoseContext] =
    useState<GlucoseContext>("fasting");
  const [measuredAt, setMeasuredAt] = useState(nowLocalInput);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const parsed = Number(value);
    if (!value || !Number.isFinite(parsed)) {
      setError("Enter a numeric value.");
      return;
    }
    setSubmitting(true);
    try {
      await createVital(memberId, {
        vital_type: vitalType,
        value_num: parsed,
        ...(vitalType === "blood_pressure"
          ? { value_secondary: Number(secondary) || undefined }
          : {}),
        ...(VITAL_UNITS[vitalType] ? { unit: VITAL_UNITS[vitalType] } : {}),
        ...(vitalType === "blood_glucose"
          ? { glucose_context: glucoseContext }
          : {}),
        measured_at: new Date(measuredAt).toISOString(),
      });
      setValue("");
      setSecondary("");
      setMeasuredAt(nowLocalInput());
      onLogged();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not log the reading.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border bg-card p-4 shadow-sm"
      aria-label="Log reading"
    >
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Plus className="size-4 text-primary" aria-hidden />
        Log reading
      </h3>
      <div className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="space-y-1.5 text-sm font-medium">
          Type
          <select
            value={vitalType}
            onChange={(e) => setVitalType(e.target.value as VitalType)}
            className={INPUT_CLASS}
          >
            {VITAL_TYPES.map((type) => (
              <option key={type} value={type}>
                {VITAL_TYPE_META[type].label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          Value
          <input
            required
            type="number"
            inputMode="decimal"
            step="any"
            placeholder={
              vitalType === "blood_pressure"
                ? "Systolic"
                : VITAL_UNITS[vitalType]
            }
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        {vitalType === "blood_pressure" && (
          <label className="space-y-1.5 text-sm font-medium">
            Diastolic
            <input
              type="number"
              inputMode="decimal"
              step="any"
              placeholder="Diastolic"
              value={secondary}
              onChange={(e) => setSecondary(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
        )}
        {vitalType === "blood_glucose" && (
          <label className="space-y-1.5 text-sm font-medium">
            Context
            <select
              value={glucoseContext}
              onChange={(e) =>
                setGlucoseContext(e.target.value as GlucoseContext)
              }
              className={INPUT_CLASS}
            >
              {GLUCOSE_CONTEXTS.map((context) => (
                <option key={context} value={context}>
                  {GLUCOSE_CONTEXT_LABELS[context]}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="space-y-1.5 text-sm font-medium">
          Measured at
          <input
            type="datetime-local"
            value={measuredAt}
            onChange={(e) => setMeasuredAt(e.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {submitting && (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          )}
          Save reading
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
