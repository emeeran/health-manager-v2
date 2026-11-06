import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { downloadCsv } from "../../lib/export";
import { todayIso } from "../../lib/utils";
import {
  SLOT_LABELS,
  medicationDurationLabel,
  medicationSlotTime,
  usedMedicationSlots,
  type Medication,
} from "../../lib/types/medication";

/**
 * Downloads the medicine schedule table (one row per active medicine, one
 * column per dose time) as CSV — the export half of the Medicines page's
 * print/export pair. The printed card stays grouped by dose time.
 */
export function ExportMedicinesButton({
  memberId,
  medications,
  className,
}: {
  memberId: string;
  medications?: Medication[];
  className?: string;
}) {
  const [busy, setBusy] = useState(false);

  const exportCsv = async () => {
    setBusy(true);
    try {
      const active = (medications ?? []).filter(
        (med) => med.status === "active",
      );
      downloadCsv(
        exportFilename(memberId),
        csvRows(active, usedMedicationSlots(active)),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void exportCsv()}
      disabled={busy || !medications?.length}
      className={
        className ??
        "flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
      }
    >
      {busy ? (
        <Loader2 className="size-4 animate-spin" aria-hidden />
      ) : (
        <Download className="size-4" aria-hidden />
      )}
      Export CSV
    </button>
  );
}

function exportFilename(memberId: string): string {
  const date = todayIso();
  return `medicine-schedule-${memberId.slice(0, 8)}-${date}.csv`;
}

function csvRows(
  meds: Medication[],
  slots: ReturnType<typeof usedMedicationSlots>,
): (string | number | null)[][] {
  const rows: (string | number | null)[][] = [
    [
      "Type",
      "Medicine",
      "Dose",
      ...slots.map((s) => SLOT_LABELS[s]),
      "Food",
      "Duration",
      "Rx by",
    ],
  ];
  for (const med of meds) {
    rows.push([
      med.dose_form,
      med.medicine,
      med.dosage,
      ...slots.map((slot) =>
        med.schedule_json?.slots?.includes(slot)
          ? medicationSlotTime(med, slot)
          : null,
      ),
      med.timing,
      medicationDurationLabel(med),
      med.provider_name,
    ]);
  }
  return rows;
}
