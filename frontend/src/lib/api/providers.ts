import { apiRequest } from "../api-client";
import type {
  Provider,
  ProviderAssignment,
  ProviderCreate,
  ProviderUpdate,
} from "../types/provider";

export function listProviders(): Promise<Provider[]> {
  return apiRequest<Provider[]>("/providers");
}

export function createProvider(input: ProviderCreate): Promise<Provider> {
  return apiRequest<Provider>("/providers", { method: "POST", body: input });
}

export function updateProvider(
  id: string,
  input: ProviderUpdate,
): Promise<Provider> {
  return apiRequest<Provider>(`/providers/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: input,
  });
}

export function deleteProvider(id: string): Promise<void> {
  return apiRequest<void>(`/providers/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listAssignments(
  memberId: string,
): Promise<ProviderAssignment[]> {
  return apiRequest<ProviderAssignment[]>(
    `/members/${encodeURIComponent(memberId)}/providers`,
  );
}

export function assignProvider(
  memberId: string,
  providerId: string,
  uhid?: string,
): Promise<ProviderAssignment> {
  return apiRequest<ProviderAssignment>(
    `/members/${encodeURIComponent(memberId)}/providers`,
    {
      method: "POST",
      body: { provider_id: providerId, ...(uhid ? { uhid } : {}) },
    },
  );
}

export function unassignProvider(
  memberId: string,
  assignmentId: string,
): Promise<void> {
  return apiRequest<void>(
    `/members/${encodeURIComponent(memberId)}/providers/${encodeURIComponent(assignmentId)}`,
    { method: "DELETE" },
  );
}
