import { apiRequest } from "../api-client";
import type { DatabaseIntegrity } from "../types/database";

/** Read-only structural integrity scan — safe for any authenticated user. */
export function getDatabaseIntegrity(): Promise<DatabaseIntegrity> {
  return apiRequest<DatabaseIntegrity>("/database/integrity");
}
