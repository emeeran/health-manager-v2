import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Users } from "lucide-react";
import type { MemberScore } from "../../lib/types/dashboard";

const MEMBER_COLORS = [
  "#6366f1",
  "#f59e0b",
  "#10b981",
  "#ec4899",
  "#8b5cf6",
  "#14b8a6",
];

const RADAR_LABELS: Record<string, string> = {
  bmi: "BMI",
  conditions_management: "Conditions",
  lab_compliance: "Labs",
  medication_tracking: "Meds",
  profile_completeness: "Profile",
  record_recency: "Recency",
};

const TOOLTIP_STYLE = {
  backgroundColor: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--foreground)",
} as const;

/**
 * Radar/spider comparison of family members' health-score breakdowns
 * (0–100 per axis). Rendered only when ≥2 members share breakdown keys.
 */
export default function FamilyRadar({
  scores,
  keys,
}: {
  scores: MemberScore[];
  keys: string[];
}) {
  const chartData = keys.map((key) => {
    const row: Record<string, string | number> = {
      axis: RADAR_LABELS[key] ?? key,
    };
    for (const score of scores) {
      const breakdown = score.score_breakdown?.[key];
      row[score.name ?? score.member_id] = breakdown
        ? Math.round((breakdown.score / breakdown.max) * 100)
        : 0;
    }
    return row;
  });

  return (
    <figure className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <figcaption className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Users className="size-4 text-primary" aria-hidden />
        Family comparison
      </figcaption>
      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis
            dataKey="axis"
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={{ fontSize: 9, fill: "var(--muted-foreground)" }}
            tickCount={5}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend
            wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
            iconType="circle"
            iconSize={6}
          />
          {scores.map((score, index) => {
            const name = score.name ?? score.member_id;
            const color = MEMBER_COLORS[index % MEMBER_COLORS.length];
            return (
              <Radar
                key={name}
                name={name}
                dataKey={name}
                stroke={color}
                fill={color}
                fillOpacity={0.12}
                strokeWidth={1.5}
              />
            );
          })}
        </RadarChart>
      </ResponsiveContainer>
    </figure>
  );
}
