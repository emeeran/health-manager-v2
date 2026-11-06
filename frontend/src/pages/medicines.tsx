import { Pill, Printer } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import useSWR from "swr";
import { ExportMedicinesButton } from "../components/medicines/export-medicines-button";
import { MedicationManager } from "../components/medicines/medication-manager";
import type { Medication } from "../lib/types/medication";
import type { Member } from "../lib/types/member";

export default function Medicines() {
  const { data: members, isLoading: membersLoading } =
    useSWR<Member[]>("/members");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Default the picker to the first household member until a choice is made.
  const memberId = selectedId ?? members?.[0]?.id ?? "";

  const {
    data: medications,
    isLoading: medicationsLoading,
    mutate,
  } = useSWR<Medication[]>(
    memberId ? `/members/${memberId}/medications` : null,
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Pill className="size-6 text-primary" aria-hidden />
            Medicines
          </h1>
          <p className="text-sm text-muted-foreground">
            The medicine schedule as one editable table, with export and print.
          </p>
        </div>
        {memberId && (
          <div className="flex items-center gap-2">
            <ExportMedicinesButton
              memberId={memberId}
              medications={medications}
            />
            <Link
              to={`/members/${memberId}/medicine-schedule`}
              className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
            >
              <Printer className="size-4" aria-hidden />
              Print
            </Link>
          </div>
        )}
      </div>

      {membersLoading ? (
        <p className="p-4 text-sm text-muted-foreground">Loading members…</p>
      ) : !members || members.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          Add a family member first, then track their medicines here.
        </p>
      ) : (
        <>
          <label className="block max-w-xs space-y-1.5 text-sm font-medium">
            Member
            <select
              value={memberId}
              onChange={(e) => setSelectedId(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            >
              {members.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name}
                </option>
              ))}
            </select>
          </label>

          {memberId && (
            <MedicationManager
              memberId={memberId}
              medications={medications}
              isLoading={medicationsLoading}
              onChange={() => {
                void mutate();
              }}
            />
          )}
        </>
      )}
    </div>
  );
}
