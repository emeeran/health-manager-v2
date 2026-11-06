/**
 * Catalogue of the /ai-tools suite: one card per tool, grouped for the hub
 * page. Pure data + helpers so the hub and tests can share them.
 */

import {
  ClipboardCheck,
  ClipboardList,
  FileSearch,
  FileStack,
  FileText,
  HeartPulse,
  IndianRupee,
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
    title: "Doctor visit summary",
    description: "Summary of one specific visit — diagnosis, treatment and follow-up",
    icon: ClipboardList,
    path: "/ai-tools/visit-summary",
  },
  {
    title: "Drug interactions",
    description: "Check current medications for potential interactions",
    icon: Pill,
    path: "/ai-tools/drug-interactions",
  },
  {
    title: "Interaction — any two medicines",
    description: "Interaction check for any two medicines you name",
    icon: Pill,
    path: "/ai-tools/drug-interaction-pair",
  },
  {
    title: "Medicine information",
    description: "Complete authenticated information on a medicine",
    icon: FileSearch,
    path: "/ai-tools/drug-info",
  },
  {
    title: "Price comparison",
    description: "Jan Aushadhi price table for your medicines",
    icon: IndianRupee,
    path: "/ai-tools/price-comparison",
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
      "/ai-tools/visit-summary",
    ],
  },
  {
    label: "Medicine reports",
    paths: [
      "/ai-tools/drug-interactions",
      "/ai-tools/drug-interaction-pair",
      "/ai-tools/drug-info",
      "/ai-tools/price-comparison",
    ],
  },
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
