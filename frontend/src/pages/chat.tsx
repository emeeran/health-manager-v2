import { Loader2, MessageCircle } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { ChatComposer } from "../components/chat/chat-composer";
import { CompendiumLookup } from "../components/chat/compendium-lookup";
import { MessageBubble } from "../components/chat/chat-message";
import { ChatSidebar } from "../components/chat/chat-sidebar";
import {
  createConversation,
  deleteConversation,
  listMessages,
  streamChatMessage,
} from "../lib/api/chat";
import type { ChatMessage, ChatSource, Conversation } from "../lib/types/chat";
import type { Member } from "../lib/types/member";
import { errorMessage } from "../lib/utils";

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
      setError(errorMessage(err, "Could not start chat."));
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
      setError(errorMessage(err, "Delete failed."));
    }
  }

  return (
    <div className="flex h-full min-h-0 gap-6">
      <ChatSidebar
        members={members}
        conversations={conversations}
        isLoading={conversationsLoading}
        selectedId={selectedId}
        memberFilter={memberFilter}
        onMemberFilterChange={setMemberFilter}
        creating={creating}
        onNewChat={() => void newChat()}
        onSelect={setSelectedId}
        onDelete={(id) => void removeConversation(id)}
        error={error}
      />

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
        errorMessage(err, "Could not get a reply."),
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

        <ChatComposer
          value={draft}
          onChange={setDraft}
          onSubmit={(event) => void handleSubmit(event)}
          streaming={streaming}
          lookupOpen={lookupOpen}
          onToggleLookup={() => setLookupOpen((open) => !open)}
        />
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
