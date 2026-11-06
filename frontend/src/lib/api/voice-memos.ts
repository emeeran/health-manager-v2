import type { VoiceMemoTranscription } from "../types/voice-memo";
import { postStream, toApiError } from "./sse";

const TRANSCRIBE_TIMEOUT_MS = 5 * 60_000;

/**
 * Upload recorded audio for transcription. `apiRequest` cannot send
 * multipart bodies, so this performs the fetch directly — keeping the same
 * cookie auth and a single refresh-and-retry on 401.
 *
 * Rejects with an `ApiError` carrying status 501 when the server has no
 * faster-whisper installed.
 */
export async function transcribeVoiceMemo(
  memberId: string,
  blob: Blob,
  language?: string,
): Promise<VoiceMemoTranscription> {
  const form = new FormData();
  form.append("audio", blob, "memo.webm");
  if (language) form.append("language", language);

  const path = `/members/${encodeURIComponent(memberId)}/voice-memos`;
  const timeout = AbortSignal.timeout(TRANSCRIBE_TIMEOUT_MS);

  const response = await postStream(path, { body: form, signal: timeout });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as VoiceMemoTranscription;
}
