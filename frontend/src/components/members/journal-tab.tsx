import SymptomJournal from "../symptoms/symptom-journal";
import VaccinationsSection from "../vaccinations/vaccinations-section";
import GrowthChart from "../growth/growth-chart";
import MilestonesCard from "../growth/milestones-card";
import ImmunizationCard from "../growth/immunization-card";

/** Journal tab: symptom diary, vaccinations, growth percentiles, milestones
 *  and the immunization schedule. */
export function JournalTab({ memberId }: { memberId: string }) {
  return (
    <div className="space-y-8">
      <SymptomJournal memberId={memberId} />
      <GrowthChart memberId={memberId} />
      <MilestonesCard memberId={memberId} />
      <ImmunizationCard memberId={memberId} />
      <VaccinationsSection memberId={memberId} />
    </div>
  );
}
