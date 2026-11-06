import { apiRequest } from "../api-client";
import type {
  GrowthReport,
  ImmunizationSchedule,
  MilestonesResponse,
} from "../types/growth";

export function getGrowthReport(memberId: string): Promise<GrowthReport> {
  return apiRequest<GrowthReport>(
    `/members/${encodeURIComponent(memberId)}/growth/report`,
  );
}

export function getMilestones(memberId: string): Promise<MilestonesResponse> {
  return apiRequest<MilestonesResponse>(
    `/members/${encodeURIComponent(memberId)}/milestones`,
  );
}

export function setMilestone(
  memberId: string,
  milestoneKey: string,
  body: { achieved: boolean; achieved_on?: string | null },
): Promise<{ key: string; achieved: boolean }> {
  return apiRequest<{ key: string; achieved: boolean }>(
    `/members/${encodeURIComponent(memberId)}/milestones/${encodeURIComponent(milestoneKey)}`,
    { method: "PUT", body },
  );
}

export function getImmunizationSchedule(
  memberId: string,
): Promise<ImmunizationSchedule> {
  return apiRequest<ImmunizationSchedule>(
    `/members/${encodeURIComponent(memberId)}/immunizations/schedule`,
  );
}
