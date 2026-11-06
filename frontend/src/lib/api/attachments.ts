import { ApiError } from "../api-client";
import { refresh } from "./auth";
import type { Attachment } from "../types/attachment";

const BASE_URL = "/api/v1";

/**
 * Upload one or more files as record attachments (multipart, repeatable
 * `files` field).
 *
 * `apiRequest` is JSON-only, so this performs the fetch directly — keeping the
 * same cookie auth and a single refresh-and-retry on 401.
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
  let response = await send(path, form);
  if (response.status === 401 && (await refresh().catch(() => false))) {
    response = await send(path, form);
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
  return (await response.json()) as Attachment[];
}

function send(path: string, form: FormData): Promise<Response> {
  return fetch(`${BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
}

/** Download URL (Content-Disposition: attachment). */
export function attachmentDownloadUrl(attachmentId: string): string {
  return `${BASE_URL}/attachments/${encodeURIComponent(attachmentId)}/download`;
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
