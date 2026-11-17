import { Loader2, MessageCircle, MessageSquarePlus, Trash2 } from "lucide-react";
import { INPUT_CLASS, cn } from "../../lib/utils";
import type { Conversation } from "../../lib/types/chat";
import type { Member } from "../../lib/types/member";

/**
 * Conversation list: family/member scope filter, new-chat button, and the
 * selectable conversation list. Data and mutations stay in the page; this is
 * the presentational shell.
 */
export function ChatSidebar({
  members,
  conversations,
  isLoading,
  selectedId,
  memberFilter,
  onMemberFilterChange,
  creating,
  onNewChat,
  onSelect,
  onDelete,
  error,
}: {
  members: Member[] | undefined;
  conversations: Conversation[] | undefined;
  isLoading: boolean;
  selectedId: string | null;
  memberFilter: string;
  onMemberFilterChange: (memberId: string) => void;
  creating: boolean;
  onNewChat: () => void;
  onSelect: (conversationId: string) => void;
  onDelete: (conversationId: string) => void;
  error: string | null;
}) {
  const memberName = (id: string | null) =>
    id ? (members ?? []).find((m) => m.id === id)?.name : "Family";

  return (
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
          onClick={onNewChat}
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
          onChange={(e) => onMemberFilterChange(e.target.value)}
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
        {isLoading ? (
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
                    onClick={() => onSelect(conversation.id)}
                    className="min-w-0 flex-1 truncate text-left"
                  >
                    {conversation.title ?? "Untitled chat"}
                    <span className="block truncate text-[11px] font-normal text-muted-foreground">
                      {memberName(conversation.member_id)}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(conversation.id)}
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
  );
}
