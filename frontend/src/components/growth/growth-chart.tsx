import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import useSWR from "swr";
import { Baby, Loader2 } from "lucide-react";
import { getGrowthReport } from "../../lib/api/growth";
import { buildGrowthSeries, rowsForMeasure } from "../../lib/growth-series";
import {
  GROWTH_MEASURE_LABELS,
  GROWTH_MEASURE_ORDER,
  GROWTH_MEASURE_UNITS,
  growthBand,
  latestGrowthRows,
  type GrowthMeasure,
} from "../../lib/types/growth";

const PRIMARY = "var(--primary)";
const MUTED = "var(--muted-foreground)";
const GRID = "var(--border)";

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

// Band fills: amber outside 15–85, green inside. Match GROWTH_BANDS hues.
const BAND_FILLS = ["#fbbf24", "#34d399", "#34d399", "#fbbf24"];

function firstAvailableMeasure(
  rows: { measure: string }[],
): GrowthMeasure | null {
  for (const measure of GROWTH_MEASURE_ORDER) {
    if (rows.some((row) => row.measure === measure)) return measure;
  }
  return null;
}

/**
 * CDC percentile-band chart for one growth measure: shaded 3rd/15th/50th/85th/97th
 * bands (approximated from the report's LMS values) with the child's readings
 * drawn over them. A single percentile is context, not a diagnosis.
 */
export default function GrowthChart({ memberId }: { memberId: string }) {
  const {
    data: report,
    isLoading,
    error,
  } = useSWR(
    memberId ? ["growth-report", memberId] : null,
    ([, id]: [string, string]) => getGrowthReport(id),
  );
  const [measure, setMeasure] = useState<GrowthMeasure | null>(null);

  const available = useMemo(
    () => (report ? firstAvailableMeasure(report.rows) : null),
    [report],
  );
  const activeMeasure = measure ?? available;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading growth data…
      </div>
    );
  }

  if (error || !report || report.rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center">
        <Baby className="mx-auto size-8 text-muted-foreground" aria-hidden />
        <p className="mt-2 text-sm font-medium">No growth data yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {report?.note ??
            "Log weight, height or head circumference readings in Trends to see CDC percentiles here."}
        </p>
      </div>
    );
  }

  const measures = GROWTH_MEASURE_ORDER.filter((m) =>
    report.rows.some((row) => row.measure === m),
  );
  const series = activeMeasure
    ? buildGrowthSeries(rowsForMeasure(report, activeMeasure))
    : null;
  const unit = activeMeasure ? GROWTH_MEASURE_UNITS[activeMeasure] : "";
  const latest = latestGrowthRows(report.rows);

  return (
    <section aria-label="Growth chart" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div
          role="group"
          aria-label="Growth measure"
          className="flex rounded-lg border border-border bg-card p-0.5"
        >
          {measures.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={option === activeMeasure}
              onClick={() => setMeasure(option)}
              className={
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors " +
                (option === activeMeasure
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground")
              }
            >
              {GROWTH_MEASURE_LABELS[option]}
            </button>
          ))}
        </div>
        {report.age_months != null && (
          <p className="text-xs text-muted-foreground">
            CDC reference · {report.age_months} months
          </p>
        )}
      </div>

      <figure className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <figcaption className="mb-2 flex flex-wrap items-baseline justify-between gap-2 text-sm font-semibold">
          {activeMeasure ? GROWTH_MEASURE_LABELS[activeMeasure] : "Growth"}
          <span className="text-xs font-normal text-muted-foreground">
            {unit}
          </span>
        </figcaption>
        {series ? (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart
              data={series.points}
              margin={{ top: 8, right: 8, bottom: 0, left: -18 }}
            >
              <CartesianGrid
                stroke={GRID}
                strokeDasharray="3 3"
                vertical={false}
              />
              <XAxis
                dataKey="ageMonths"
                {...AXIS_PROPS}
                minTickGap={24}
                tickFormatter={(value: number) => `${Math.round(value)}m`}
              />
              <YAxis {...AXIS_PROPS} width={48} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(value, name) => {
                  const numeric = Number(value);
                  const label = String(name);
                  return [
                    Number.isFinite(numeric)
                      ? Number.isInteger(numeric)
                        ? numeric
                        : numeric.toFixed(1)
                      : value,
                    label === "reading" ? "Reading" : `${label} percentile`,
                  ] as [string | number, string];
                }}
                labelFormatter={(label) => `${String(label)} months`}
              />
              {/* Invisible base anchors the stacked bands at the 3rd percentile. */}
              <Area
                dataKey="base"
                stackId="band"
                stroke="none"
                fill="transparent"
                legendType="none"
              />
              {(["b1", "b2", "b3", "b4"] as const).map((band, index) => (
                <Area
                  key={band}
                  dataKey={band}
                  stackId="band"
                  stroke="none"
                  fill={BAND_FILLS[index]}
                  fillOpacity={0.18}
                  legendType="none"
                />
              ))}
              <Line
                type="monotone"
                dataKey="reading"
                name="reading"
                stroke={PRIMARY}
                strokeWidth={2}
                dot={{ r: 3.5, fill: PRIMARY, strokeWidth: 0 }}
                activeDot={{ r: 4 }}
                connectNulls
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="p-6 text-center text-sm text-muted-foreground">
            Not enough readings for this measure yet.
          </p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block size-2 rounded-sm bg-primary"
            />
            Reading
          </span>
          {BAND_FILLS.map((fill, index) => (
            <span key={fill + index} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className="inline-block size-2 rounded-sm"
                style={{ backgroundColor: fill, opacity: 0.5 }}
              />
              {["3rd–15th", "15th–85th", "50th band", "85th–97th"][index]}
            </span>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Bands approximate the CDC 2000 reference from the report's LMS values.
          A single percentile is context, not a diagnosis — discuss the trend
          with your pediatrician.
        </p>
      </figure>

      {/* Latest assessment chips */}
      {latest.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {latest.map((row) => {
            const band = growthBand(row.percentile);
            return (
              <li
                key={row.measure}
                className="flex items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2 shadow-sm"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {GROWTH_MEASURE_LABELS[row.measure] ?? row.measure}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {row.value} · {row.measured_at}
                    {row.implausible && (
                      <span className="ml-1 font-medium text-danger">
                        (implausible — check the recording)
                      </span>
                    )}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${band.chip}`}
                >
                  {row.percentile}th · {band.text}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
