import { ArrowLeft, Printer } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { MedicineScheduleCard } from "../components/medicines/medicine-schedule-card";
import { useEscapeNavigation } from "../hooks/use-escape-navigation";

/**
 * Printable medicine schedule (print/export from the Medicines page). Lives
 * outside AppLayout so the sidebar and header never appear in print output;
 * the card itself comes from MedicineScheduleCard.
 */
export default function MedicineSchedule() {
  const { memberId = "" } = useParams();
  // Outside AppLayout, so Esc-to-go-back is wired here explicitly.
  useEscapeNavigation();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between print:hidden">
        <Link
          to="/medicines"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Back to medicines
        </Link>
        <button
          type="button"
          onClick={() => window.print()}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Printer className="size-4" aria-hidden />
          Print / Save PDF
        </button>
      </div>

      <MedicineScheduleCard memberId={memberId} />
    </div>
  );
}
