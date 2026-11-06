import { describe, expect, it } from "vitest";
import { AI_TOOLS, TOOL_GROUPS, toolPath, toolsFor } from "../ai-tools";
import { reportKindPath } from "../api/insights";
import { SEVERITY_STYLES } from "../types/drug-interaction";
import { INSIGHT_KIND_META, INSIGHT_KINDS } from "../types/insight";

describe("tool catalogue", () => {
  it("every group path resolves to a catalogue card", () => {
    for (const group of TOOL_GROUPS) {
      expect(toolsFor(group).length).toBe(group.paths.length);
    }
  });

  it("every catalogue card belongs to exactly one group", () => {
    const grouped = TOOL_GROUPS.flatMap((group) => group.paths);
    expect(new Set(grouped).size).toBe(grouped.length);
    expect(new Set(grouped)).toEqual(
      new Set(AI_TOOLS.map((tool) => tool.path)),
    );
  });

  it("appends the selected member to a tool path", () => {
    expect(toolPath("/ai-tools/smart-report")).toBe("/ai-tools/smart-report");
    expect(toolPath("/ai-tools/smart-report", "m-1")).toBe(
      "/ai-tools/smart-report?memberId=m-1",
    );
  });
});

describe("report kind paths", () => {
  it("keeps the contracted slug for the original smart report", () => {
    expect(reportKindPath("smart_report")).toBe("smart");
  });

  it("derives kebab-case slugs for the newer kinds", () => {
    expect(reportKindPath("pre_consultation")).toBe("pre-consultation");
    expect(reportKindPath("consultant_note")).toBe("consultant-note");
    expect(reportKindPath("consolidated_report")).toBe("consolidated-report");
    expect(reportKindPath("medication_report")).toBe("medication-report");
  });
});

describe("insight kinds", () => {
  it("has human metadata for every kind", () => {
    for (const kind of INSIGHT_KINDS) {
      expect(INSIGHT_KIND_META[kind].label.length).toBeGreaterThan(0);
      expect(INSIGHT_KIND_META[kind].description.length).toBeGreaterThan(0);
    }
  });
});

describe("severity styles", () => {
  it("covers every interaction severity", () => {
    expect(Object.keys(SEVERITY_STYLES).sort()).toEqual([
      "high",
      "low",
      "moderate",
    ]);
  });
});
