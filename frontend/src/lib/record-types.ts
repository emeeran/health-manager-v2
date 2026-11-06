import {
  File,
  FileText,
  FlaskConical,
  Pill,
  Scan,
  Stethoscope,
  Syringe,
  type LucideIcon,
} from "lucide-react";
import type { RecordType } from "./types/record";

export const RECORD_TYPE_META: Record<
  RecordType,
  { label: string; icon: LucideIcon }
> = {
  doctor_visit: { label: "Doctor visit", icon: Stethoscope },
  lab_report: { label: "Lab report", icon: FlaskConical },
  prescription: { label: "Prescription", icon: Pill },
  discharge_summary: { label: "Discharge summary", icon: FileText },
  imaging: { label: "Imaging", icon: Scan },
  vaccination: { label: "Vaccination", icon: Syringe },
  other: { label: "Other", icon: File },
};

/** Metadata for a record type, falling back to `other` for unknown values. */
export function recordTypeMeta(recordType: string): {
  label: string;
  icon: LucideIcon;
} {
  return RECORD_TYPE_META[recordType as RecordType] ?? RECORD_TYPE_META.other;
}
