/** Progress stages streamed while an extraction runs. */
export type ExtractStage = "reading" | "extracting" | "verifying";

export interface ExtractStageEvent {
  stage: ExtractStage;
  message: string;
}

export interface ExtractionResult {
  clinical_data: Record<string, unknown>;
  summary: string | null;
  provider_used: string;
  verification_id: string | null;
}

export interface ExtractCompleteEvent {
  stage: "complete";
  result: ExtractionResult;
}

export interface ExtractErrorEvent {
  stage: "error";
  message: string;
}

/** One SSE `data:` payload from the extract stream. */
export type ExtractEvent =
  ExtractStageEvent | ExtractCompleteEvent | ExtractErrorEvent;

export type VerificationStatus = "pending" | "passed" | "flagged" | "failed";

/* ── Claim audit (audit agent) ─────────────────────────────────────── */

export type ClaimCategory =
  | "record_fact"
  | "condition"
  | "prognosis"
  | "guideline"
  | "drug_interaction"
  | "recommendation";

export type ClaimVerdict =
  | "supported"
  | "contradicted"
  | "not_in_records"
  | "external_verified"
  | "unverified";

export type AuditSeverity = "info" | "warning" | "critical";

export interface EvidenceRef {
  domain: string;
  ref: string;
  label: string;
  value: string | null;
  date: string | null;
}

export interface DataGap {
  domain: string;
  status: "missing" | "stale";
  detail: string;
}

export interface WebSource {
  title: string;
  url: string;
}

export interface WebCheck {
  query: string;
  results: WebSource[];
}

export interface ClaimAudit {
  claim: string;
  category: ClaimCategory;
  verdict: ClaimVerdict;
  severity: AuditSeverity;
  evidence_ids: string[];
  evidence: EvidenceRef[];
  needs_web: boolean;
  web_query: string | null;
  web: WebCheck | null;
  note: string | null;
}

export interface AuditReport {
  overall: "passed" | "flagged" | "failed";
  summary: string;
  claims: ClaimAudit[];
  gaps: DataGap[];
  /** Pairwise interaction rows from the existing analyser (shape varies). */
  interactions: Record<string, unknown>[];
  web_used: boolean;
  sources: WebSource[];
}

export interface Verification {
  id: string;
  status: VerificationStatus;
  notes: string | null;
  /** Model that ran the check, when the backend reports it. */
  verifier_name?: string | null;
  /** Claim-level audit for reports, health Q&A and chat; null for extractions. */
  audit?: AuditReport | null;
}

export interface AiProvider {
  name: string;
  available: boolean;
  local: boolean;
  model: string;
}

export interface AiStatus {
  default_provider: string | null;
  providers: AiProvider[];
}
