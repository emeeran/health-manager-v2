import { apiRequest } from "../api-client";
import type { DashboardSummary } from "../types/dashboard";

/** Aggregated household dashboard: alerts, scores, activity, reminders. */
export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiRequest<DashboardSummary>("/dashboard");
}
