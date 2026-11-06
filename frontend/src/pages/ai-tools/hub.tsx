import { ChevronRight, Loader2, Sparkles, Users } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { toolsFor, TOOL_GROUPS, toolPath } from "../../lib/ai-tools";
import { listMembers } from "../../lib/api/members";
import type { Member } from "../../lib/types/member";

/** /ai-tools hub: card grid linking every AI tool page. */
export default function AiToolsHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: members, isLoading } = useSWR<Member[]>(
    "/members",
    listMembers,
  );

  const memberId = searchParams.get("memberId") ?? "";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Sparkles className="size-6 text-primary" aria-hidden />
          AI tools
        </h1>
        <p className="text-sm text-muted-foreground">
          AI-powered health tools, scoped to one family member at a time
        </p>
      </header>

      <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <label className="flex flex-wrap items-center gap-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Member
          {isLoading ? (
            <span className="flex items-center gap-2 text-sm normal-case">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Loading members…
            </span>
          ) : (
            <select
              value={memberId}
              onChange={(e) =>
                setSearchParams(
                  e.target.value ? { memberId: e.target.value } : {},
                  { replace: true },
                )
              }
              className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm font-normal normal-case outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Choose a family member…</option>
              {(members ?? []).map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name}
                </option>
              ))}
            </select>
          )}
        </label>
      </div>

      {TOOL_GROUPS.map((group) => (
        <section
          key={group.label}
          aria-label={group.label}
          className="space-y-3"
        >
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {group.label}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {toolsFor(group).map((tool) => {
              const Icon = tool.icon;
              return (
                <Link
                  key={tool.path}
                  to={toolPath(tool.path, memberId)}
                  className="group rounded-xl border border-border bg-card p-4 shadow-sm transition-colors hover:border-primary/40"
                >
                  <div className="flex items-center gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <p className="min-w-0 flex-1 text-sm font-semibold">
                      {tool.title}
                    </p>
                    <ChevronRight
                      className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                      aria-hidden
                    />
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {tool.description}
                  </p>
                </Link>
              );
            })}
          </div>
        </section>
      ))}

      {!isLoading && members?.length === 0 && (
        <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
          <Users className="mx-auto size-8" aria-hidden />
          <span className="mt-2 block">
            No family members yet — add one from the Members page to use the AI
            tools.
          </span>
        </p>
      )}
    </div>
  );
}
