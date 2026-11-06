import { ChevronLeft } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { listMembers } from "../../lib/api/members";
import type { Member } from "../../lib/types/member";

const inputClass =
  "rounded-lg border border-input bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring";

/**
 * Shared chrome for /ai-tools/* pages: back link, title, and a member
 * picker synced to the `?memberId=` query param. Children render below
 * only once a member is chosen.
 */
export function AiToolPage({
  title,
  children,
}: {
  title: string;
  children: (memberId: string) => React.ReactNode;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: members } = useSWR<Member[]>("/members", listMembers);

  const memberId = searchParams.get("memberId") ?? members?.[0]?.id ?? "";

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link
            to="/ai-tools"
            aria-label="Back to AI tools"
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ChevronLeft className="size-4" aria-hidden />
          </Link>
          <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        </div>
        <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          Member
          <select
            value={memberId}
            onChange={(e) =>
              setSearchParams(
                e.target.value ? { memberId: e.target.value } : {},
                { replace: true },
              )
            }
            className={inputClass}
          >
            {!members?.length && <option value="">No members</option>}
            {(members ?? []).map((member) => (
              <option key={member.id} value={member.id}>
                {member.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {memberId ? (
        children(memberId)
      ) : (
        <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
          Add a family member first — AI tools run on one member's records.
        </p>
      )}
    </div>
  );
}
