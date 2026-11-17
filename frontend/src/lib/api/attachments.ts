import { ApiError } from "../api-client";
import { refresh } from "./auth";
import type { Attachment } from "../types/attachment";

const BASE_URL = "/api/v1";

/**
 * Upload files as record attachments (multipart, repeatable `files` field) or
 * download one as a Blob.
 *
 * `apiRequest` is JSON-only, so these perform the fetch directly — keeping the
 * same cookie auth, a single refresh-and-retry on 401, and `ApiError` details.
 */
export async function uploadAttachments(
  memberId: string,
  recordId: string,
  files: File[],
): Promise<Attachment[]> {
  if (files.length === 0) return [];
  const form = new FormData();
  for (const file of files) form.append("files", file);

  const path = `/members/${encodeURIComponent(memberId)}/records/${encodeURIComponent(recordId)}/attachments`;
  const response = await sendWithRefresh(path, { method: "POST", body: form });
  return (await response.json()) as Attachment[];
}

/** Download an attachment (Content-Disposition: attachment) as a Blob. */
export async function downloadAttachment(attachmentId: string): Promise<Blob> {
  const path = `/attachments/${encodeURIComponent(attachmentId)}/download`;
  const response = await sendWithRefresh(path);
  return await response.blob();
}

/** Download URL (Content-Disposition: attachment), for plain `<a href>` links. */
export function attachmentDownloadUrl(attachmentId: string): string {
  return `${BASE_URL}/attachments/${encodeURIComponent(attachmentId)}/download`;
}

async function sendWithRefresh(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  let response = await send(path, init);
  if (response.status === 401 && (await refresh().catch(() => false))) {
    response = await send(path, init);
  }
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, detail);
  }
  return response;
}

function send(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${BASE_URL}${path}`, { credentials: "include", ...init });
}

/** Inline URL, suitable for `<img>` / `<iframe>` (cookies sent automatically). */
export function attachmentPreviewUrl(attachmentId: string): string {
  return `${BASE_URL}/attachments/${encodeURIComponent(attachmentId)}/preview`;
}

/** Rendered thumbnail (image/webp, 300px). */
export function attachmentThumbnailUrl(attachmentId: string): string {
  return `${BASE_URL}/attachments/${encodeURIComponent(attachmentId)}/thumbnail`;
}

/** Single PDF page render (image/png), 0-based page number. */
export function attachmentPageUrl(
  attachmentId: string,
  pageNumber: number,
): string {
  return `${BASE_URL}/attachments/${encodeURIComponent(attachmentId)}/pages/${pageNumber}`;
}
