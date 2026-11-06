import { BookOpen, Loader2, Search, X } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { useEscClose } from "../../hooks/use-esc-close";
import {
  listMemberResources,
  searchDrugs,
  type DrugSearchResult,
} from "../../lib/api/drugs";
import { INPUT_CLASS } from "../../lib/utils";

/**
 * Minimal reference-lookup side panel for chat: search the household's drug
 * compendium and (when a member is scoped) list their reference resources.
 * Deliberately light — a full dialog was more surface than chat needs.
 */
export function CompendiumLookup({
  memberId,
  onClose,
}: {
  memberId?: string | null;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  // Escape closes the side panel (routed through the global overlay stack).
  useEscClose(true, onClose);
  const trimmed = query.trim();
  const { data: drugs, isLoading } = useSWR<DrugSearchResult[]>(
    trimmed.length >= 2 ? ["drugs-search", trimmed] : null,
    () => searchDrugs(trimmed),
  );
  const { data: resources } = useSWR(
    memberId ? ["member-resources", memberId] : null,
    () => listMemberResources(memberId!),
  );

  return (
    <aside
      aria-label="Reference lookup"
      className="flex w-72 shrink-0 flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <BookOpen className="size-4 text-primary" aria-hidden />
          Reference lookup
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close lookup panel"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>

      <label className="relative block">
        <span className="sr-only">Search drugs</span>
        <Search
          className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground"
          aria-hidden
        />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search drugs…"
          className={`${INPUT_CLASS} pl-8`}
        />
      </label>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
        {trimmed.length >= 2 &&
          (isLoading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
              Searching…
            </p>
          ) : !drugs || drugs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No drug matches.</p>
          ) : (
            <ul className="space-y-1.5">
              {drugs.map((drug, index) => (
                <li
                  key={drug.name ?? index}
                  className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
                >
                  <p className="font-medium">{drug.name}</p>
                  {drug.summary && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {drug.summary}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          ))}

        {memberId && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Member resources
            </p>
            {!resources || resources.length === 0 ? (
              <p className="mt-1.5 text-sm text-muted-foreground">
                No reference documents for this member.
              </p>
            ) : (
              <ul className="mt-1.5 space-y-1">
                {resources.map((resource, index) => (
                  <li
                    key={resource.id ?? index}
                    className="flex items-center gap-1.5 text-sm text-muted-foreground"
                  >
                    <BookOpen className="size-3.5 shrink-0" aria-hidden />
                    <span className="min-w-0 truncate">
                      {resource.title ?? resource.filename ?? resource.id}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
