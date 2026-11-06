import { ApiError } from "../api-client";
import type { PublicShare } from "../types/share";
import { toApiError } from "./sse";

/**
 * Fetch the emergency summary behind a share token.
 *
 * Deliberately bypasses `apiRequest` and `postStream`: the visitor has no
 * session, so a 401 refresh-and-redirect-to-login would be wrong here —
 * failures surface as errors the share page renders in place.
 */
export async function getPublicShare(token: string): Promise<PublicShare> {
  let response: Response;
  try {
    response = await fetch(
      `/api/v1/public/share/${encodeURIComponent(token)}`,
      { credentials: "include" },
    );
  } catch (error) {
    throw new ApiError(
      0,
      undefined,
      error instanceof Error ? error.message : "Network error",
    );
  }
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as PublicShare;
}
