import {
  Eye,
  File,
  FlaskConical,
  Stethoscope,
  type LucideIcon,
} from "lucide-react";
import type { RecordType } from "./types/record";

export const RECORD_TYPE_META: Record<
  RecordType,
  { label: string; icon: LucideIcon }
> = {
  doctor_visit: { label: "Visit to Doctor", icon: Stethoscope },
  eye_checkup: { label: "Eye Check Up", icon: Eye },
  lab_test: { label: "Lab Test", icon: FlaskConical },
  other: { label: "Others", icon: File },
};

/** Metadata for a record type, falling back to `other` for unknown values. */
export function recordTypeMeta(recordType: string): {
  label: string;
  icon: LucideIcon;
} {
  return RECORD_TYPE_META[recordType as RecordType] ?? RECORD_TYPE_META.other;
}
