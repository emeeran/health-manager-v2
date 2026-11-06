import { Loader2, Pill, RefreshCw, ShieldAlert, Sparkles } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import {
  checkDrugInteractions,
  getLatestDrugInteractions,
} from "../../lib/api/drug-interactions";
import type {
  DrugInteraction,
  DrugInteractionResponse,
} from "../../lib/types/drug-interaction";
import { SEVERITY_STYLES } from "../../lib/types/drug-interaction";
import { formatYearMonthDay } from "../../lib/utils";
import { Markdown } from "../shared/markdown";

/**
 * Drug-interaction tool body: check the member's active medications and
 * render severity-color-coded interaction cards.
 */
export function DrugInteractionsView({ memberId }: { memberId: string }) {
  const { data: cached, mutate } = useSWR<DrugInteractionResponse | null>(
    ["drug-interactions", "latest", memberId],
    () => getLatestDrugInteractions(memberId),
  );
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DrugInteractionResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  async function handleCheck() {
    setRunning(true);
    setRunError(null);
    try {
      const fresh = await checkDrugInteractions(memberId);
      setResult(fresh);
      await mutate(fresh, { revalidate: false });
    } catch (err) {
      setRunError(
        err instanceof Error ? err.message : "Interaction check failed.",
      );
    } finally {
      setRunning(false);
    }
  }

  const shown = result ?? cached ?? null;

  return (
    <div className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Screen the active medication list for known interactions.
        </p>
        <button
          type="button"
          onClick={() => void handleCheck()}
          disabled={running}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : cached ? (
            <RefreshCw className="size-4" aria-hidden />
          ) : (
            <Sparkles className="size-4" aria-hidden />
          )}
          {running ? "Checking…" : cached ? "Re-check" : "Check interactions"}
        </button>
      </div>

      {runError && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {runError}
        </p>
      )}

      {!running &&
        (shown ? (
          <InteractionResults result={shown} />
        ) : (
          <p className="text-sm text-muted-foreground">
            No check yet — run it against this member's active medications.
          </p>
        ))}
    </div>
  );
}

function InteractionResults({ result }: { result: DrugInteractionResponse }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {result.medications_checked} medication
        {result.medications_checked === 1 ? "" : "s"} checked
        {result.cached_at
          ? ` · last checked ${formatYearMonthDay(result.cached_at)}`
          : ""}
      </p>
      {result.interactions.length === 0 ? (
        <p className="rounded-lg bg-primary/10 px-3 py-2 text-sm text-primary">
          No known interactions found among the active medications.
        </p>
      ) : (
        <ul className="space-y-2">
          {result.interactions.map((interaction, index) => (
            <InteractionCard
              key={(interaction.drugs ?? []).join("+") + index}
              interaction={interaction}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function InteractionCard({ interaction }: { interaction: DrugInteraction }) {
  // Older persisted rows predate the drugs/description contract — render
  // them defensively instead of crashing on undefined arrays.
  const drugs = interaction.drugs ?? [];
  const description =
    interaction.description ??
    (interaction as { interaction?: string }).interaction ??
    "";
  return (
    <li className="rounded-xl border border-border bg-background p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${
            SEVERITY_STYLES[interaction.severity] ?? SEVERITY_STYLES.moderate
          }`}
        >
          <ShieldAlert className="size-3.5" aria-hidden />
          {interaction.severity}
        </span>
        <span className="flex items-center gap-1.5 text-sm font-semibold">
          <Pill className="size-4 text-muted-foreground" aria-hidden />
          {drugs.length > 0 ? drugs.join(" + ") : "Interaction"}
        </span>
        {interaction.source && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {interaction.source === "drugbank"
              ? `DrugBank${interaction.evidence_level ? ` ${interaction.evidence_level}` : ""}`
              : "AI estimate"}
          </span>
        )}
      </div>
      {description && (
        <div className="mt-2 text-sm">
          <Markdown>{description}</Markdown>
        </div>
      )}
      {interaction.recommendation && (
        <div className="mt-1.5 text-sm text-muted-foreground [&_p]:my-0">
          <Markdown>{interaction.recommendation}</Markdown>
        </div>
      )}
    </li>
  );
}
