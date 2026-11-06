export type HouseholdRole = "admin" | "member" | "viewer";

export interface HouseholdInfo {
  id: string;
  name: string;
  my_role: HouseholdRole;
}

export interface HouseholdUpdate {
  name: string;
}

export interface HouseholdUser {
  user_id: string;
  username: string;
  role: HouseholdRole;
  is_primary: boolean;
  created_at: string;
}

export interface InvitationCreated {
  id: string;
  /** Shown exactly once at creation; the server only stores a hash. */
  token: string;
  role: HouseholdRole;
  expires_at: string;
}

export interface InvitationInfo {
  id: string;
  role: HouseholdRole;
  expires_at: string;
  accepted: boolean;
  created_at: string;
}

export interface AiProviderConfig {
  name: string;
  enabled: boolean;
  model?: string | null;
  base_url?: string | null;
}

export type PrimaryProvider =
  | "auto"
  | "cloud"
  | "local"
  | "openai"
  | "groq"
  | "gemini"
  | "cohere"
  | "deepseek"
  | "mistral"
  | "openrouter"
  | "huggingface"
  | "ollama";

export interface AiProviderStatus {
  name: string;
  model: string;
  local: boolean;
}

export interface AiProviderTestResult {
  ok: boolean;
  latency_ms: number;
  model: string;
  error: string | null;
}

export interface AiConfig {
  primary_provider: PrimaryProvider;
  providers: AiProviderConfig[];
}

export interface ProviderKeyStatus {
  name: string;
  set: boolean;
  source: "db" | "env" | "none";
  value: string;
}

/** Instance capability for the audit agent's optional web fact-checking. */
export interface WebFactcheckStatus {
  enabled: boolean;
  configured: boolean;
  max_claims: number;
  max_results: number;
}
