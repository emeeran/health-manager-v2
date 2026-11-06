import { apiRequest } from "../api-client";
import type { Member, MemberCreate, MemberUpdate } from "../types/member";

export function listMembers(): Promise<Member[]> {
  return apiRequest<Member[]>("/members");
}

export function getMember(id: string): Promise<Member> {
  return apiRequest<Member>(`/members/${encodeURIComponent(id)}`);
}

export function createMember(input: MemberCreate): Promise<Member> {
  return apiRequest<Member>("/members", { method: "POST", body: input });
}

export function updateMember(id: string, input: MemberUpdate): Promise<Member> {
  return apiRequest<Member>(`/members/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: input,
  });
}

export function mergeCurrentMedications(
  id: string,
): Promise<{ suggestion: string }> {
  return apiRequest<{ suggestion: string }>(
    `/members/${encodeURIComponent(id)}/current-medications/merge`,
    { method: "POST" },
  );
}

export function deleteMember(id: string): Promise<void> {
  return apiRequest<void>(`/members/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
