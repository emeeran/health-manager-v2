import { apiRequest } from "../api-client";
import type { ShareLinkCreated } from "../types/share";

export function createShareLink(
  memberId: string,
  expiresDays?: number,
): Promise<ShareLinkCreated> {
  return apiRequest<ShareLinkCreated>(
    `/members/${encodeURIComponent(memberId)}/share-links`,
    {
      method: "POST",
      body: expiresDays === undefined ? {} : { expires_days: expiresDays },
    },
  );
}

export function revokeShareLink(
  memberId: string,
  linkId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/share-links/${encodeURIComponent(linkId)}`,
    { method: "DELETE" },
  );
}
