import { apiRequest, ApiError } from "../api-client";
import type { ChatMessage, ChatStreamEvent, Conversation } from "../types/chat";
import { consumeSse, postStream, STREAM_TIMEOUT_MS, toApiError } from "./sse";

export function createConversation(input: {
  member_id?: string | null;
  title?: string;
}): Promise<Conversation> {
  return apiRequest<Conversation>("/conversations", {
    method: "POST",
    body: input,
  });
}

export function listMessages(conversationId: string): Promise<ChatMessage[]> {
  return apiRequest<ChatMessage[]>(
    `/conversations/${encodeURIComponent(conversationId)}/messages`,
  );
}

export function deleteConversation(conversationId: string): Promise<void> {
  return apiRequest<void>(
    `/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" },
  );
}

export interface StreamChatOptions {
  signal?: AbortSignal;
}

/**
 * Send a user message and consume the SSE reply stream, invoking `onEvent`
 * per parsed event. Resolves with the `complete` event's message; rejects on
 * stream, HTTP, or `error`-stage failures.
 *
 * `apiRequest` cannot stream, so this performs the fetch directly — keeping
 * the same cookie auth and a single refresh-and-retry on 401 (same shape as
 * `streamExtract`).
 */
export async function streamChatMessage(
  conversationId: string,
  content: string,
  onEvent: (event: ChatStreamEvent) => void,
  { signal }: StreamChatOptions = {},
): Promise<ChatMessage> {
  const path = `/conversations/${encodeURIComponent(conversationId)}/messages/stream`;
  const timeout = AbortSignal.timeout(STREAM_TIMEOUT_MS);

  const response = await postStream(path, {
    body: JSON.stringify({ content }),
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
  if (!response.ok) {
    throw await toApiError(response);
  }

  let message: ChatMessage | null = null;
  await consumeSse<ChatStreamEvent>(
    response,
    (event) => {
      if (event.stage === "complete") message = event.message;
      if (event.stage === "error") {
        throw new ApiError(0, undefined, event.message);
      }
      onEvent(event);
    },
    "Empty chat stream.",
  );

  if (!message) {
    throw new ApiError(0, undefined, "Chat stream ended without a reply.");
  }
  return message;
}
