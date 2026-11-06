import { Loader2, Pencil } from "lucide-react";
import { useState, type FormEvent } from "react";
import { updateMember } from "../../lib/api/members";
import { useEscClose } from "../../hooks/use-esc-close";
import { RELATIONSHIPS, SEXES, type Member } from "../../lib/types/member";
import { INPUT_CLASS } from "../../lib/utils";

/**
 * Edit dialog for a member profile: prefilled from the current member,
 * PATCH on save. Mirrors the quick-add form's styling; the extra ICE and
 * growth fields (sex, phone, blood group, emergency contacts, notes) only
 * surface here — the quick-add stays minimal.
 */
export function MemberEditDialog({
  member,
  onClose,
  onSaved,
}: {
  member: Member;
  onClose: () => void;
  onSaved: (member: Member) => void;
}) {
  const [name, setName] = useState(member.name);
  const [relationship, setRelationship] = useState(member.relationship);
  const [birthDate, setBirthDate] = useState(member.birth_date ?? "");
  const [sex, setSex] = useState(member.sex ?? "");
  const [phone, setPhone] = useState(member.phone ?? "");
  const [bloodGroup, setBloodGroup] = useState(member.blood_group ?? "");
  const [emergencyName, setEmergencyName] = useState(
    member.emergency_contact_name ?? "",
  );
  const [emergencyPhone, setEmergencyPhone] = useState(
    member.emergency_contact_phone ?? "",
  );
  const [notes, setNotes] = useState(member.notes ?? "");
  const [webFactcheckConsent, setWebFactcheckConsent] = useState(
    member.web_factcheck_consent ?? false,
  );

  // Escape closes the dialog (routed through the global overlay stack).
  useEscClose(true, onClose);
  const [medicalHistory, setMedicalHistory] = useState(
    member.medical_history ?? "",
  );
  const [familyMedicalHistory, setFamilyMedicalHistory] = useState(
    member.family_medical_history ?? "",
  );
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const saved = await updateMember(member.id, {
        name,
        relationship,
        birth_date: birthDate || null,
        sex: sex || null,
        phone: phone || null,
        blood_group: bloodGroup || null,
        emergency_contact_name: emergencyName || null,
        emergency_contact_phone: emergencyPhone || null,
        medical_history: medicalHistory || null,
        family_medical_history: familyMedicalHistory || null,
        notes: notes || null,
        web_factcheck_consent: webFactcheckConsent,
      });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save changes.");
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      onClick={onClose}
      data-testid="member-edit-dialog"
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        aria-label={`Edit ${member.name}`}
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-border bg-card p-5 shadow-lg"
      >
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
          <Pencil className="size-4" aria-hidden />
          Edit member
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1.5 text-sm font-medium">
            Full name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Relationship
            <select
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
              className={`${INPUT_CLASS} capitalize`}
            >
              {RELATIONSHIPS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Birth date
            <input
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Sex{" "}
            <span className="font-normal text-muted-foreground">
              (growth charts)
            </span>
            <select
              value={sex}
              onChange={(e) => setSex(e.target.value)}
              className={`${INPUT_CLASS} capitalize`}
            >
              <option value="">Unknown</option>
              {SEXES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Phone
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Blood group
            <input
              placeholder="e.g. O+"
              value={bloodGroup}
              onChange={(e) => setBloodGroup(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Emergency contact
            <input
              aria-label="Emergency contact name"
              value={emergencyName}
              onChange={(e) => setEmergencyName(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Emergency phone
            <input
              value={emergencyPhone}
              onChange={(e) => setEmergencyPhone(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
            Medical history
            <textarea
              rows={3}
              placeholder="Conditions, surgeries, chronic diagnoses — feeds the ICE card and preventive-care rules."
              value={medicalHistory}
              onChange={(e) => setMedicalHistory(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
            Family medical history
            <textarea
              rows={3}
              placeholder="Conditions, surgeries, chronic diagnoses in the family…"
              value={familyMedicalHistory}
              onChange={(e) => setFamilyMedicalHistory(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
            Notes
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="flex items-start gap-2 text-sm sm:col-span-2">
            <input
              type="checkbox"
              checked={webFactcheckConsent}
              onChange={(e) => setWebFactcheckConsent(e.target.checked)}
              className="mt-1"
            />
            <span>
              <span className="font-medium">Allow external fact-checking</span>
              <span className="block text-xs font-normal text-muted-foreground">
                Lets the audit agent search a self-hosted SearXNG instance for
                guideline checks. Queries are redacted in code: no names,
                dates, or identifiers are sent. Off unless you opt in.
              </span>
            </span>
          </label>
        </div>
        {error && (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {error}
          </p>
        )}
        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {submitting && (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            )}
            Save changes
          </button>
        </div>
      </form>
    </div>
  );
}
