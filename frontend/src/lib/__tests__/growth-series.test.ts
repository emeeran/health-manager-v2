import { describe, expect, it } from "vitest";
import {
  buildGrowthSeries,
  lmsValueAt,
  rowsForMeasure,
} from "../growth-series";
import type { GrowthRow } from "../types/growth";

function row(
  ageMonths: number,
  measure = "weight",
  overrides: Partial<GrowthRow> = {},
): GrowthRow {
  return {
    measure,
    measured_at: `2026-01-${String((ageMonths % 28) + 1).padStart(2, "0")}`,
    value: 10,
    age_months: ageMonths,
    z: 0,
    percentile: 50,
    implausible: false,
    lms: { l: 1, m: 10, s: 0.1 },
    ...overrides,
  };
}

describe("lmsValueAt", () => {
  it("returns the median at z=0", () => {
    expect(lmsValueAt(1, 10, 0.1, 0)).toBeCloseTo(10, 5);
  });

  it("applies the power formula for nonzero L", () => {
    // M * (1 + L*S*z)^(1/L) = 10 * (1 + 1*0.1*1)^1 = 11
    expect(lmsValueAt(1, 10, 0.1, 1)).toBeCloseTo(11, 5);
  });

  it("uses the exponential form when L is zero", () => {
    expect(lmsValueAt(0, 10, 0.1, 1)).toBeCloseTo(10 * Math.exp(0.1), 5);
  });
});

describe("buildGrowthSeries", () => {
  it("returns null without rows", () => {
    expect(buildGrowthSeries([])).toBeNull();
  });

  it("builds monotonic percentile band boundaries for linear LMS", () => {
    const series = buildGrowthSeries([row(6), row(12)]);
    expect(series).not.toBeNull();
    for (const point of series!.points) {
      expect(point.p3).toBeLessThan(point.p15);
      expect(point.p15).toBeLessThan(point.p50);
      expect(point.p50).toBeLessThan(point.p85);
      expect(point.p85).toBeLessThan(point.p97);
    }
    expect(series!.points[0].reading).toBe(10);
    expect(series!.readings).toEqual([
      { ageMonths: 6, value: 10 },
      { ageMonths: 12, value: 10 },
    ]);
  });

  it("uses each assessment age's LMS values for band medians", () => {
    const series = buildGrowthSeries([
      row(6, "weight", { lms: { l: 1, m: 8, s: 0.1 } }),
      row(12, "weight", { lms: { l: 1, m: 10, s: 0.1 } }),
    ]);
    const at6 = series!.points.find((point) => point.ageMonths === 6);
    const at12 = series!.points.find((point) => point.ageMonths === 12);
    expect(at6?.p50).toBeCloseTo(8, 5);
    expect(at12?.p50).toBeCloseTo(10, 5);
  });
});

describe("rowsForMeasure", () => {
  it("filters rows by measure", () => {
    const rows = [row(6, "weight"), row(6, "stature")];
    expect(rowsForMeasure({ age_months: 6, rows }, "stature")).toHaveLength(1);
    expect(rowsForMeasure({ age_months: 6, rows }, "stature")[0].measure).toBe(
      "stature",
    );
  });
});
