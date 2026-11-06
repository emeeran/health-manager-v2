import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  GLUCOSE_CONTEXT_LABELS,
  type GlucoseContext,
  type Vital,
} from "../../lib/types/vital";
import { bandColor, type ReferenceRanges } from "../../lib/types/reference";

/**
 * Chart palette — `--primary` is read through the CSS theme; fixed hues are
 * used where recharts needs concrete, non-inheritable SVG fills.
 */
const PRIMARY = "var(--primary)";
const MUTED = "var(--muted-foreground)";
const GRID = "var(--border)";
const DIASTOLIC = "#7c3aed";
const CONTEXT_COLORS: Record<GlucoseContext, string> = {
  fasting: "#d97706",
  post_prandial: "#7c3aed",
  random: "var(--primary)",
};

const AXIS_PROPS = {
  stroke: GRID,
  tick: { fill: MUTED, fontSize: 11 },
  tickLine: false,
} as const;

const TOOLTIP_STYLE = {
  backgroundColor: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--foreground)",
} as const;

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

function shortDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE_FORMAT.format(date);
}

function byMeasuredAsc(a: Vital, b: Vital): number {
  return new Date(a.measured_at).getTime() - new Date(b.measured_at).getTime();
}

function ofType(vitals: Vital[], type: Vital["vital_type"]): Vital[] {
  return vitals.filter((vital) => vital.vital_type === type);
}

interface BpPoint {
  label: string;
  systolic: number;
  diastolic: number;
}

function buildBpPoints(vitals: Vital[]): BpPoint[] {
  return ofType(vitals, "blood_pressure")
    .sort(byMeasuredAsc)
    .map((vital) => ({
      label: shortDate(vital.measured_at),
      systolic: vital.value_num,
      diastolic: vital.value_secondary ?? 0,
    }));
}

function bpDomain(vitals: Vital[], ranges?: ReferenceRanges): [number, number] {
  const bp = ofType(vitals, "blood_pressure");
  let max = 0;
  for (const vital of bp) {
    max = Math.max(max, vital.value_num, vital.value_secondary ?? 0);
  }
  if (ranges) {
    for (const band of ranges.blood_pressure.bands)
      max = Math.max(max, band.max_systolic);
  }
  const top = Math.min(220, Math.ceil((max + 15) / 10) * 10);
  return [Math.max(40, top - 160), top];
}

function BloodPressureChart({
  vitals,
  ranges,
}: {
  vitals: Vital[];
  ranges?: ReferenceRanges;
}) {
  const points = buildBpPoints(vitals);
  if (points.length === 0) return null;
  const bands = ranges?.blood_pressure.bands ?? [];
  const [domainMin, domainMax] = bpDomain(vitals, ranges);

  return (
    <ChartCard
      title="Blood pressure"
      unit="mmHg"
      footnote={bands.at(-1)?.citation}
    >
      <ResponsiveContainer width="100%" height={260}>
        <LineChart
          data={points}
          margin={{ top: 8, right: 8, bottom: 0, left: -18 }}
        >
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" {...AXIS_PROPS} minTickGap={28} />
          <YAxis domain={[domainMin, domainMax]} {...AXIS_PROPS} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          {bands.map((band, index) => (
            <ReferenceArea
              key={band.label}
              y1={index === 0 ? domainMin : bands[index - 1].max_systolic}
              y2={band.max_systolic}
              fill={bandColor(band.color_key, index)}
              fillOpacity={0.07}
              stroke="none"
              ifOverflow="extendDomain"
            />
          ))}
          <Line
            type="monotone"
            dataKey="systolic"
            name="Systolic"
            stroke={PRIMARY}
            strokeWidth={2}
            dot={{ r: 3, fill: PRIMARY, strokeWidth: 0 }}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="diastolic"
            name="Diastolic"
            stroke={DIASTOLIC}
            strokeWidth={2}
            dot={{ r: 3, fill: DIASTOLIC, strokeWidth: 0 }}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

interface GlucosePoint {
  label: string;
  fasting?: number;
  post_prandial?: number;
  random?: number;
}

function buildGlucosePoints(vitals: Vital[]): GlucosePoint[] {
  return ofType(vitals, "blood_glucose")
    .sort(byMeasuredAsc)
    .map((vital) => ({
      label: shortDate(vital.measured_at),
      ...(vital.glucose_context
        ? { [vital.glucose_context]: vital.value_num }
        : { random: vital.value_num }),
    }));
}

function GlucoseChart({
  vitals,
  ranges,
}: {
  vitals: Vital[];
  ranges?: ReferenceRanges;
}) {
  const points = buildGlucosePoints(vitals);
  if (points.length === 0) return null;
  const fasting = ranges?.blood_glucose.fasting;
  const unit = fasting?.unit ?? "mg/dL";

  return (
    <ChartCard title="Blood glucose" unit={unit}>
      <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {(Object.keys(CONTEXT_COLORS) as GlucoseContext[]).map((context) => (
          <span key={context} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block size-2 rounded-full"
              style={{ backgroundColor: CONTEXT_COLORS[context] }}
            />
            {GLUCOSE_CONTEXT_LABELS[context]}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart
          data={points}
          margin={{ top: 8, right: 8, bottom: 0, left: -18 }}
        >
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" {...AXIS_PROPS} minTickGap={28} />
          <YAxis {...AXIS_PROPS} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          {fasting && (
            <ReferenceArea
              y1={fasting.normal_low}
              y2={fasting.normal_high}
              fill={PRIMARY}
              fillOpacity={0.08}
              stroke="none"
              ifOverflow="extendDomain"
            />
          )}
          {(Object.keys(CONTEXT_COLORS) as GlucoseContext[]).map((context) => (
            <Line
              key={context}
              type="monotone"
              dataKey={context}
              name={GLUCOSE_CONTEXT_LABELS[context]}
              stroke={CONTEXT_COLORS[context]}
              strokeWidth={1.5}
              dot={{ r: 3.5, fill: CONTEXT_COLORS[context], strokeWidth: 0 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

interface AreaSeries {
  type: Vital["vital_type"];
  title: string;
  color: string;
}

const AREA_SERIES: AreaSeries[] = [
  { type: "weight", title: "Weight", color: "#0ea5e9" },
  { type: "heart_rate", title: "Heart rate", color: "#e11d48" },
  { type: "spo2", title: "SpO2", color: "#0d9488" },
  { type: "hba1c", title: "HbA1c", color: "#d97706" },
];

function AreaCard({ vitals, series }: { vitals: Vital[]; series: AreaSeries }) {
  const readings = ofType(vitals, series.type).sort(byMeasuredAsc);
  if (readings.length === 0) return null;
  const points = readings.map((vital) => ({
    label: shortDate(vital.measured_at),
    value: vital.value_num,
  }));

  return (
    <ChartCard title={series.title}>
      <ResponsiveContainer width="100%" height={150}>
        <AreaChart
          data={points}
          margin={{ top: 4, right: 8, bottom: 0, left: -24 }}
        >
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" {...AXIS_PROPS} minTickGap={24} />
          <YAxis {...AXIS_PROPS} width={48} domain={["auto", "auto"]} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Area
            type="monotone"
            dataKey="value"
            name={series.title}
            stroke={series.color}
            fill={series.color}
            fillOpacity={0.12}
            strokeWidth={2}
            dot={{ r: 2.5, fill: series.color, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function ChartCard({
  title,
  unit,
  footnote,
  children,
}: {
  title: string;
  unit?: string;
  footnote?: string;
  children: React.ReactNode;
}) {
  return (
    <figure className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <figcaption className="mb-2 flex items-baseline justify-between text-sm font-semibold">
        {title}
        {unit && (
          <span className="text-xs font-normal text-muted-foreground">
            {unit}
          </span>
        )}
      </figcaption>
      {children}
      {footnote && (
        <p className="mt-2 text-xs text-muted-foreground">{footnote}</p>
      )}
    </figure>
  );
}

export default function VitalsCharts({
  vitals,
  ranges,
}: {
  vitals: Vital[];
  ranges?: ReferenceRanges;
}) {
  return (
    <div className="space-y-4">
      <BloodPressureChart vitals={vitals} ranges={ranges} />
      <GlucoseChart vitals={vitals} ranges={ranges} />
      <div className="grid gap-4 sm:grid-cols-2">
        {AREA_SERIES.map((series) => (
          <AreaCard key={series.type} vitals={vitals} series={series} />
        ))}
      </div>
    </div>
  );
}
