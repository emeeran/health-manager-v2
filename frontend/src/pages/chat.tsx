import {
  BookOpen,
  Loader2,
  MessageCircle,
  MessageSquarePlus,
  PanelRight,
  Send,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Markdown } from "../components/shared/markdown";
import useSWR, { mutate as globalMutate } from "swr";
import { CompendiumLookup } from "../components/chat/compendium-lookup";
import { AuditPanel } from "../components/reports/audit-panel";
import {
  createConversation,
  deleteConversation,
  listMessages,
  streamChatMessage,
} from "../lib/api/chat";
import { getVerification } from "../lib/api/ai";
import type { ChatMessage, ChatSource, Conversation } from "../lib/types/chat";
import type { Member } from "../lib/types/member";
import type { VerificationStatus } from "../lib/types/ai";
import { INPUT_CLASS, cn } from "../lib/utils";

export default function Chat() {
  const { data: members } = useSWR<Member[]>("/members");
  const [memberFilter, setMemberFilter] = useState<string>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const listKey = "/conversations";
  const {
    data: allConversations,
    isLoading: conversationsLoading,
    mutate: mutateList,
  } = useSWR<Conversation[]>(listKey);
  // A member filter narrows member-scoped chats but keeps family-wide ones
  // visible — a general conversation is relevant under any member scope,
  // and strict filtering makes an open chat "vanish" from the list.
  const conversations = allConversations?.filter(
    (c) =>
      !memberFilter || c.member_id === null || c.member_id === memberFilter,
  );
  const memberName = (id: string | null) =>
    id ? (members ?? []).find((m) => m.id === id)?.name : "Family";

  async function newChat() {
    setCreating(true);
    setError(null);
    try {
      const conversation = await createConversation({
        member_id: memberFilter || null,
      });
      await mutateList();
      setSelectedId(conversation.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start chat.");
    } finally {
      setCreating(false);
    }
  }

  async function removeConversation(conversationId: string) {
    if (!window.confirm("Delete this conversation?")) return;
    try {
      await deleteConversation(conversationId);
      if (selectedId === conversationId) setSelectedId(null);
      await mutateList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  }

  return (
    <div className="flex h-full min-h-0 gap-6">
      <aside
        aria-label="Conversations"
        className="flex w-64 shrink-0 flex-col gap-3"
      >
        <div className="flex items-center justify-between">
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <MessageCircle className="size-5 text-primary" aria-hidden />
            Chat
          </h1>
          <button
            type="button"
            onClick={() => void newChat()}
            disabled={creating}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {creating ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : (
              <MessageSquarePlus className="size-3.5" aria-hidden />
            )}
            New chat
          </button>
        </div>

        <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
          Scope to member
          <select
            value={memberFilter}
            onChange={(e) => setMemberFilter(e.target.value)}
            className={INPUT_CLASS}
          >
            <option value="">All family</option>
            {(members ?? []).map((member) => (
              <option key={member.id} value={member.id}>
                {member.name}
              </option>
            ))}
          </select>
        </label>

        {error && (
          <p
            role="alert"
            className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger"
          >
            {error}
          </p>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {conversationsLoading ? (
            <p className="p-3 text-sm text-muted-foreground">Loading…</p>
          ) : !conversations || conversations.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border bg-card p-4 text-center text-sm text-muted-foreground">
              No conversations yet.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <div
                    className={cn(
                      "group flex items-center gap-1 rounded-lg border px-3 py-2 text-sm transition-colors",
                      selectedId === conversation.id
                        ? "border-primary/50 bg-primary/10 text-primary"
                        : "border-border bg-card text-foreground hover:border-primary/50",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedId(conversation.id)}
                      className="min-w-0 flex-1 truncate text-left"
                    >
                      {conversation.title ?? "Untitled chat"}
                      <span className="block truncate text-[11px] font-normal text-muted-foreground">
                        {memberName(conversation.member_id)}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => void removeConversation(conversation.id)}
                      aria-label="Delete conversation"
                      className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100 hover:text-danger"
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {selectedId ? (
        <ChatThread
          key={selectedId}
          conversationId={selectedId}
          memberId={
            conversations?.find((c) => c.id === selectedId)?.member_id ?? null
          }
          onChanged={() => {
            void mutateList();
            void globalMutate(listKey);
          }}
        />
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center">
            <MessageCircle
              className="mx-auto size-8 text-muted-foreground"
              aria-hidden
            />
            <p className="mt-2 text-sm font-medium">
              Ask about any family member's health
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Pick a conversation or start a new one.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/** Exported for tests: the message-list fetcher wiring has regressed once. */
export function ChatThread({
  conversationId,
  memberId,
  onChanged,
}: {
  conversationId: string;
  memberId: string | null;
  onChanged: () => void;
}) {
  const {
    data: messages,
    isLoading,
    mutate,
  } = useSWR<ChatMessage[]>(
    `/conversations/${conversationId}/messages`,
    // Fetcher closes over the id: SWR would otherwise pass the full key
    // string as `conversationId`, double-encoding it into a 404 URL.
    () => listMessages(conversationId),
  );
  const [draft, setDraft] = useState("");
  const [streamText, setStreamText] = useState<string | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [freshSources, setFreshSources] = useState<ChatSource[] | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [lookupOpen, setLookupOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const streaming = streamText !== null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages?.length, streamText]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || streaming) return;
    setDraft("");
    setSendError(null);
    setStreamText("");
    setPhase("thinking");
    setFreshSources(null);
    try {
      await streamChatMessage(conversationId, content, (event) => {
        if (event.stage === "streaming") {
          setPhase(null);
          setStreamText((prev) => (prev ?? "") + event.delta);
        } else if (event.stage === "complete") {
          // RAG citations ride along on the complete event; the persisted
          // message may carry them too, in which case the bubble uses its own.
          if (event.sources?.length) setFreshSources(event.sources);
        } else {
          setPhase(event.stage);
        }
      });
      await mutate();
      onChanged();
    } catch (err) {
      setSendError(
        err instanceof Error ? err.message : "Could not get a reply.",
      );
      await mutate(); // still pick up the user message the server stored
    } finally {
      setStreamText(null);
      setPhase(null);
    }
  }

  return (
    <div className="flex min-w-0 flex-1 gap-3">
      <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-border bg-card shadow-sm">
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Loading conversation…
            </div>
          ) : !messages || messages.length === 0 ? (
            <p className="p-10 text-center text-sm text-muted-foreground">
              Ask anything about this family's records — medications, allergies,
              past visits.
            </p>
          ) : (
            messages.map((message, index) => (
              <MessageBubble
                key={message.id}
                message={message}
                memberId={memberId}
                sources={
                  message.sources ??
                  // The just-finished reply's citations arrive on the complete
                  // event; fall back to them until history carries them too.
                  (index === messages.length - 1
                    ? (freshSources ?? undefined)
                    : undefined)
                }
              />
            ))
          )}

          {streaming && (
            <MessageBubble
              message={{
                id: "streaming",
                role: "assistant",
                content: streamText ?? "",
                created_at: "",
                verification: null,
              }}
              memberId={memberId}
              pendingLabel={phase ? `${phase}…` : null}
            />
          )}
          <div ref={bottomRef} />
        </div>

        {sendError && (
          <p
            role="alert"
            className="mx-5 mb-2 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {sendError}
          </p>
        )}

        <form onSubmit={handleSubmit} className="flex items-end gap-2 p-4">
          <label className="flex-1 space-y-1.5">
            <span className="sr-only">Message</span>
            <textarea
              rows={2}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Ask a question… (Enter to send, Shift+Enter for a new line)"
              disabled={streaming}
              className={cn(INPUT_CLASS, "resize-none")}
            />
          </label>
          <button
            type="button"
            onClick={() => setLookupOpen((open) => !open)}
            aria-label={
              lookupOpen ? "Hide reference lookup" : "Open reference lookup"
            }
            aria-pressed={lookupOpen}
            title="Reference lookup"
            className={`flex size-10 shrink-0 items-center justify-center rounded-lg border transition-colors ${
              lookupOpen
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-border bg-background text-muted-foreground hover:text-foreground"
            }`}
          >
            <PanelRight className="size-4" aria-hidden />
          </button>
          <button
            type="submit"
            disabled={streaming || !draft.trim()}
            className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            aria-label="Send message"
          >
            {streaming ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Send className="size-4" aria-hidden />
            )}
          </button>
        </form>
      </div>

      {lookupOpen && (
        <CompendiumLookup
          memberId={memberId}
          onClose={() => setLookupOpen(false)}
        />
      )}
    </div>
  );
}

function MessageBubble({
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
              <VerificationChip verification={message.verification} />
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

const VERIFICATION_LABELS: Record<VerificationStatus, string> = {
  pending: "Verifying…",
  passed: "AI-verified",
  flagged: "AI flagged",
  failed: "AI check failed",
};

const VERIFICATION_CLASSES: Record<VerificationStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  passed: "bg-primary/10 text-primary",
  flagged: "bg-warning/15 text-warning-foreground",
  failed: "bg-danger/10 text-danger",
};

/**
 * Verification state of an assistant reply. While a fresh reply is still
 * pending, polls the verification endpoint every 3s until it settles.
 */
function VerificationChip({
  verification,
}: {
  verification: NonNullable<ChatMessage["verification"]>;
}) {
  // `id` only arrives on the freshly-completed message; stored history has
  // status only, so nothing to poll there.
  const { data } = useSWR(
    verification.id && verification.status === "pending"
      ? `/verifications/${verification.id}`
      : null,
    () => getVerification(verification.id!),
    { refreshInterval: 3000 },
  );
  const status: VerificationStatus = data?.status ?? verification.status;
  const settled = status !== "pending";

  return (
    <span
      title={data?.notes ?? undefined}
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium",
        VERIFICATION_CLASSES[status],
      )}
    >
      {settled && status !== "passed" && <span aria-hidden>⚠ </span>}
      {VERIFICATION_LABELS[status]}
    </span>
  );
}
