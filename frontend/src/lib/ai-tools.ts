/**
 * Catalogue of the /ai-tools suite: one card per tool, grouped for the hub
 * page. Pure data + helpers so the hub and tests can share them.
 */

import {
  ClipboardCheck,
  FileStack,
  FileText,
  HeartPulse,
  Pill,
  Sparkles,
  Stethoscope,
  Wand2,
  type LucideIcon,
} from "lucide-react";

export interface ToolCard {
  title: string;
  description: string;
  icon: LucideIcon;
  path: string;
}

export const AI_TOOLS: ToolCard[] = [
  {
    title: "Health insights",
    description:
      "Comprehensive report from history, family history, visits, medicines and labs",
    icon: HeartPulse,
    path: "/ai-tools/health-insights",
  },
  {
    title: "Quick health summary",
    description: "Short assessment of active conditions and flagged results",
    icon: Sparkles,
    path: "/ai-tools/smart-report",
  },
  {
    title: "Consultant note",
    description: "Concise doctor-facing snapshot to share at an appointment",
    icon: Stethoscope,
    path: "/ai-tools/consultant-note",
  },
  {
    title: "Pre-consultation notes",
    description: "Prepare notes and checklists for upcoming doctor visits",
    icon: ClipboardCheck,
    path: "/ai-tools/pre-consultation",
  },
  {
    title: "Consolidated report",
    description: "Every visit, diagnosis and treatment in one ledger",
    icon: FileStack,
    path: "/ai-tools/consolidated-report",
  },
  {
    title: "Medication report",
    description: "Full medication history with dose changes over time",
    icon: Pill,
    path: "/ai-tools/medication-report",
  },
  {
    title: "Drug interactions",
    description: "Check current medications for potential interactions",
    icon: Pill,
    path: "/ai-tools/drug-interactions",
  },
  {
    title: "Smart entry",
    description: "Create structured records from plain-language descriptions",
    icon: Wand2,
    path: "/ai-tools/smart-entry",
  },
  {
    title: "Summaries",
    description: "Browse past AI narratives and insights per member",
    icon: FileText,
    path: "/ai-tools/summaries",
  },
];

export interface ToolGroup {
  label: string;
  paths: string[];
}

/** Hub sections in render order; each path list is that section's card order. */
export const TOOL_GROUPS: ToolGroup[] = [
  {
    label: "Reports",
    paths: [
      "/ai-tools/health-insights",
      "/ai-tools/smart-report",
      "/ai-tools/consultant-note",
      "/ai-tools/pre-consultation",
      "/ai-tools/consolidated-report",
      "/ai-tools/medication-report",
    ],
  },
  { label: "Safety", paths: ["/ai-tools/drug-interactions"] },
  {
    label: "Tools",
    paths: ["/ai-tools/smart-entry", "/ai-tools/summaries"],
  },
];

/** A group's cards, in the order its paths list them. */
export function toolsFor(group: ToolGroup): ToolCard[] {
  return group.paths
    .map((path) => AI_TOOLS.find((tool) => tool.path === path))
    .filter((tool): tool is ToolCard => Boolean(tool));
}

/** Append the currently selected member to a tool path. */
export function toolPath(path: string, memberId?: string): string {
  return memberId ? `${path}?memberId=${encodeURIComponent(memberId)}` : path;
}
