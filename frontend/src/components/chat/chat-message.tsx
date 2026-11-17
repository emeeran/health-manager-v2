import { useState } from "react";
import { BookOpen, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Markdown } from "../shared/markdown";
import { AuditPanel } from "../reports/audit-panel";
import { VerificationBadge } from "../verification-badge";
import type { ChatMessage, ChatSource } from "../../lib/types/chat";
import { cn } from "../../lib/utils";

/**
 * One chat bubble. User messages render as plain text with preserved
 * newlines; assistant replies render as GFM markdown (lists, tables, code)
 * with verification, audit trail, and optional RAG citations underneath.
 */
export function MessageBubble({
  message,
  memberId,
  pendingLabel,
  sources,
}: {
  message: ChatMessage;
  memberId: string | null;
  pendingLabel?: string | null;
  sources?: ChatSource[];
}) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex flex-col gap-1",
        isUser ? "items-end" : "items-start",
      )}
    >
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm",
          isUser
            ? "rounded-br-md bg-primary text-primary-foreground"
            : "rounded-bl-md bg-muted text-foreground",
        )}
      >
        {isUser ? (
          /* User messages stay plain text with preserved newlines. */
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        ) : (
          /* Assistant replies render as GFM markdown (lists, tables, code). */
          <Markdown>{message.content}</Markdown>
        )}
      </div>
      {!isUser && (
        <>
          <div className="flex items-center gap-2">
            {pendingLabel && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="size-3 animate-spin" aria-hidden />
                {pendingLabel}
              </span>
            )}
            {message.verification && (
              <VerificationBadge verification={message.verification} />
            )}
          </div>
          {message.verification?.id && (
            <AuditPanel verificationId={message.verification.id} />
          )}
          {sources && sources.length > 0 && (
            <SourcesList sources={sources} memberId={memberId} />
          )}
        </>
      )}
    </div>
  );
}

/** Collapsible list of citations shown under a grounded assistant reply. */
function SourcesList({
  sources,
  memberId,
}: {
  sources: ChatSource[];
  memberId: string | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="max-w-[80%]">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <BookOpen className="size-3" aria-hidden />
        Sources ({sources.length})
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1.5 rounded-lg border border-border bg-background p-2.5 text-xs">
          {sources.map((source, index) => {
            const chip = (
              <>
                <BookOpen className="size-3 shrink-0" aria-hidden />
                {source.source ?? "Reference"}
                {source.page != null && ` · p. ${source.page}`}
              </>
            );
            return (
              <li key={index}>
                {source.record_id ? (
                  <Link
                    to={`/members/${memberId}/records/${source.record_id}`}
                    className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-0.5 font-medium text-muted-foreground transition-colors hover:text-primary"
                  >
                    {chip}
                  </Link>
                ) : (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-0.5 font-medium text-muted-foreground">
                    {chip}
                  </span>
                )}
                {source.snippet && (
                  <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
                    {source.snippet}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
