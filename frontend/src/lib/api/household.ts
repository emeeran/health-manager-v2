import { apiRequest } from "../api-client";
import type {
  AiProviderStatus,
  AiProviderTestResult,
  AiConfig,
  HouseholdInfo,
  HouseholdRole,
  HouseholdUpdate,
  HouseholdUser,
  InvitationCreated,
  InvitationInfo,
  ProviderKeyStatus,
  WebFactcheckStatus,
} from "../types/household";

export function getHousehold(): Promise<HouseholdInfo> {
  return apiRequest<HouseholdInfo>("/household");
}

export function renameHousehold(
  input: HouseholdUpdate,
): Promise<HouseholdInfo> {
  return apiRequest<HouseholdInfo>("/household", {
    method: "PATCH",
    body: input,
  });
}

export function listHouseholdUsers(): Promise<HouseholdUser[]> {
  return apiRequest<HouseholdUser[]>("/household/users");
}

export function setUserRole(
  userId: string,
  role: HouseholdRole,
): Promise<HouseholdUser> {
  return apiRequest<HouseholdUser>(
    `/household/users/${encodeURIComponent(userId)}`,
    {
      method: "PATCH",
      body: { role },
    },
  );
}

export function removeHouseholdUser(userId: string): Promise<void> {
  return apiRequest<void>(`/household/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}

export function createInvitation(
  role: HouseholdRole,
): Promise<InvitationCreated> {
  return apiRequest<InvitationCreated>("/household/users/invitations", {
    method: "POST",
    body: { role },
  });
}

export function listInvitations(): Promise<InvitationInfo[]> {
  return apiRequest<InvitationInfo[]>("/household/users/invitations");
}

export function revokeInvitation(invitationId: string): Promise<void> {
  return apiRequest<void>(
    `/household/users/invitations/${encodeURIComponent(invitationId)}`,
    { method: "DELETE" },
  );
}

export function getAiConfig(): Promise<AiConfig> {
  return apiRequest<AiConfig>("/household/ai-config");
}

export function putAiConfig(config: AiConfig): Promise<AiConfig> {
  return apiRequest<AiConfig>("/household/ai-config", {
    method: "PUT",
    body: config,
  });
}

export function listProviderKeys(): Promise<{ keys: ProviderKeyStatus[] }> {
  return apiRequest<{ keys: ProviderKeyStatus[] }>("/system/provider-keys");
}

export function setProviderKey(
  name: string,
  value: string,
): Promise<ProviderKeyStatus> {
  return apiRequest<ProviderKeyStatus>(
    `/system/provider-keys/${encodeURIComponent(name)}`,
    { method: "PUT", body: { value } },
  );
}

export function listAiProviders(): Promise<{ providers: AiProviderStatus[] }> {
  return apiRequest<{ providers: AiProviderStatus[] }>("/system/ai-providers");
}

export function testAiProvider(name: string): Promise<AiProviderTestResult> {
  return apiRequest<AiProviderTestResult>(
    `/system/ai-providers/${encodeURIComponent(name)}/test`,
    { method: "POST" },
  );
}

/** Live model catalogue for the model picker (GET /models or /api/tags). */
export function listProviderModels(
  name: string,
): Promise<{ models: string[] }> {
  return apiRequest<{ models: string[] }>(
    `/system/ai-providers/${encodeURIComponent(name)}/models`,
  );
}

export function deleteProviderKey(name: string): Promise<ProviderKeyStatus> {
  return apiRequest<ProviderKeyStatus>(
    `/system/provider-keys/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
}

/** Instance-level status for the audit agent's SearXNG fact-checking. */
export function getWebFactcheckStatus(): Promise<WebFactcheckStatus> {
  return apiRequest<WebFactcheckStatus>("/system/web-factcheck");
}
