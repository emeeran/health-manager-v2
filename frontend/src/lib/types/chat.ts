import type { VerificationStatus } from "./ai";

export interface Conversation {
  id: string;
  member_id: string | null;
  title: string | null;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  /** `id` appears on freshly completed messages so the chip can poll. */
  verification: {
    id?: string;
    status: VerificationStatus;
    notes: string | null;
  } | null;
  /** RAG citations — present when the answer was grounded in documents. */
  sources?: ChatSource[];
}

/** One retrieved-document citation carried by the `complete` event. */
export interface ChatSource {
  page: number;
  /** Short excerpt when the server includes one; may be absent. */
  snippet?: string;
  /** Compendium/document name the citation points into, when known. */
  source?: string;
  /** Record the citation grounds in, when it points at household data. */
  record_id?: string;
}

/**
 * Progress stages carried by plain status events. `streaming` and `complete`
 * have their own event shapes, so they are not part of this union — that
 * keeps the SSE event union discriminable on `stage`.
 */
export type ChatStage = "context" | "verifying";

export interface ChatStageEvent {
  stage: ChatStage;
  message?: string;
}

export interface ChatDeltaEvent {
  stage: "streaming";
  delta: string;
}

export interface ChatCompleteEvent {
  stage: "complete";
  message: ChatMessage;
  /** RAG citations for the reply; absent when grounding is inactive. */
  sources?: ChatSource[];
}

export interface ChatErrorEvent {
  stage: "error";
  message: string;
}

/** One SSE `data:` payload from the chat stream. */
export type ChatStreamEvent =
  ChatStageEvent | ChatDeltaEvent | ChatCompleteEvent | ChatErrorEvent;
