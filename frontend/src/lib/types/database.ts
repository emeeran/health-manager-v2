/** Shape of GET /api/v1/database/integrity (backend check_integrity). */

export interface OrphanCount {
  table: string;
  column: string;
  target: string;
  count: number;
}

export interface AttachmentCheck {
  checked: number;
  missing: number;
  missing_paths: string[];
  sample_limit: number;
}

export interface DatabaseIntegrity {
  ok: boolean;
  engine: string;
  integrity_check: string[];
  orphans: OrphanCount[];
  orphan_count: number;
  attachment_check: AttachmentCheck;
  duration_ms: number;
  notes: string[];
}
