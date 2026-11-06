import {
  AlertTriangle,
  ArrowLeft,
  Loader2,
  Pill,
  Phone,
  Printer,
  Stethoscope,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import useSWR from "swr";
import QRCode from "react-qr-code";
import { getEmergencyCard } from "../lib/api/member";

function emergencyUrl(memberId: string): string {
  const base = window.location.origin;
  return `${base}/members/${memberId}/emergency`;
}

/** In-case-of-emergency card: the one-glance medical summary + QR. */
export default function MemberEmergency() {
  const { memberId = "" } = useParams();
  const {
    data: card,
    error,
    isLoading,
  } = useSWR(memberId ? `/members/${memberId}/emergency` : null, () =>
    getEmergencyCard(memberId),
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading emergency card…
      </div>
    );
  }
  if (error || !card) {
    return (
      <div className="mx-auto max-w-3xl">
        <p
          role="alert"
          className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load the emergency card.{" "}
          {error instanceof Error ? error.message : ""}
        </p>
      </div>
    );
  }

  const { member } = card;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        to={`/members/${memberId}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground print:hidden"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Back to member
      </Link>

      <div className="flex items-center justify-between print:hidden">
        <h1 className="text-2xl font-semibold tracking-tight">
          Emergency card (ICE)
        </h1>
        <button
          type="button"
          onClick={() => window.print()}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Printer className="size-4" aria-hidden />
          Print
        </button>
      </div>

      <article
        aria-label="Emergency card"
        className="space-y-5 rounded-xl border-2 border-danger/40 bg-card p-6 shadow-sm"
      >
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-danger">
              In case of emergency
            </p>
            <h2 className="text-xl font-semibold">{member.name}</h2>
            <p className="text-sm text-muted-foreground">
              {member.birth_date ? `Born ${member.birth_date}` : ""}
              {member.blood_group ? ` · Blood group ${member.blood_group}` : ""}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-white p-2">
            <span aria-label="Emergency card QR code">
              <QRCode value={emergencyUrl(memberId)} size={110} />
            </span>
          </div>
        </header>

        {(member.emergency_contact_name || member.emergency_contact_phone) && (
          <section
            aria-label="Emergency contact"
            className="flex items-center gap-3"
          >
            <Phone className="size-5 text-danger" aria-hidden />
            <div>
              <p className="text-sm font-semibold">
                {member.emergency_contact_name ?? "Emergency contact"}
              </p>
              <p className="text-sm text-muted-foreground">
                {member.emergency_contact_phone}
              </p>
            </div>
          </section>
        )}

        <CardSection
          title="Allergies"
          icon={<AlertTriangle className="size-4" aria-hidden />}
        >
          {card.allergies.length === 0 ? (
            <Empty>None recorded</Empty>
          ) : (
            <ul className="space-y-1">
              {card.allergies.map((allergy) => (
                <li key={allergy.substance} className="text-sm">
                  <span
                    className={`font-medium ${
                      allergy.severity === "severe" ? "text-danger" : ""
                    }`}
                  >
                    {allergy.substance}
                  </span>
                  <span className="text-muted-foreground">
                    {" "}
                    · {allergy.severity}
                    {allergy.reaction ? ` · ${allergy.reaction}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardSection>

        <CardSection title="Conditions" icon={null}>
          {card.conditions.length === 0 ? (
            <Empty>None recorded</Empty>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {card.conditions.map((condition) => (
                <li
                  key={condition.name}
                  className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium"
                >
                  {condition.name}
                </li>
              ))}
            </ul>
          )}
        </CardSection>

        <CardSection
          title="Current medications"
          icon={<Pill className="size-4" aria-hidden />}
        >
          {card.active_medications.length === 0 ? (
            <Empty>None recorded</Empty>
          ) : (
            <ul className="space-y-1">
              {card.active_medications.map((medication) => (
                <li key={medication.medicine} className="text-sm">
                  <span className="font-medium">{medication.medicine}</span>
                  {medication.dosage && (
                    <span className="text-muted-foreground">
                      {" "}
                      · {medication.dosage}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardSection>

        {member.medical_history && (
          <CardSection title="Medical history" icon={null}>
            <p className="text-sm text-muted-foreground">
              {member.medical_history}
            </p>
          </CardSection>
        )}

        {card.providers.length > 0 && (
          <CardSection
            title="Care team"
            icon={<Stethoscope className="size-4" aria-hidden />}
          >
            <ul className="space-y-1">
              {card.providers.map((provider) => (
                <li
                  key={`${provider.name}-${provider.uhid ?? ""}`}
                  className="text-sm"
                >
                  <span className="font-medium">{provider.name}</span>
                  <span className="text-muted-foreground">
                    {provider.specialty ? ` · ${provider.specialty}` : ""}
                    {provider.uhid ? ` · UHID ${provider.uhid}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </CardSection>
        )}
      </article>
    </div>
  );
}

function CardSection({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-1.5">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}
