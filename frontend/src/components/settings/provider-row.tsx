import {
  Check,
  ChevronDown,
  ChevronUp,
  Loader2,
  RefreshCw,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import type {
  AiProviderConfig,
  AiProviderTestResult,
  ProviderKeyStatus,
} from "../../lib/types/household";

/** One merged row of the board: failover entry, stored credentials and the
 * household override for a single provider. */
export interface ProviderRow {
  name: string;
  failover?: { model: string; local: boolean };
  override?: AiProviderConfig;
  apiKey?: ProviderKeyStatus;
  baseUrl?: ProviderKeyStatus;
}

interface ProviderRowViewProps {
  row: ProviderRow;
  /** Override model, falling back to the failover default. */
  model: string | null;
  /** 1-based position in the failover list, when the provider has an entry. */
  failoverRank?: number;
  result?: AiProviderTestResult | "testing";
  fetchingModels: boolean;
  busy: boolean;
  isExpanded: boolean;
  isFirst: boolean;
  isLast: boolean;
  onToggle: () => void;
  onTest: () => void;
  onRefreshModels: () => void;
  onMove: (dir: -1 | 1) => void;
  onSetEnabled: (enabled: boolean) => void;
  /** The expanded details panel, rendered inside the row. */
  children?: ReactNode;
}

/** One row of the provider board: status dot, model, test / refresh / reorder
 * controls, with the details panel as children when expanded. */
export function ProviderRowView({
  row,
  model,
  failoverRank,
  result,
  fetchingModels,
  busy,
  isExpanded,
  isFirst,
  isLast,
  onToggle,
  onTest,
  onRefreshModels,
  onMove,
  onSetEnabled,
  children,
}: ProviderRowViewProps) {
  return (
    <li data-testid={`provider-row-${row.name}`}>
      <div
        className={`flex flex-wrap items-center gap-2 px-3 py-2 text-xs ${
          isExpanded ? "bg-muted/30" : ""
        }`}
      >
        <KeyDot row={row} />
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isExpanded}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <span className="font-medium capitalize">{row.name}</span>
          <span className="truncate text-muted-foreground">
            {model ?? "default"}
          </span>
          {row.failover?.local && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
              local
            </span>
          )}
          {row.override && !row.override.enabled && (
            <span className="rounded-full bg-danger/10 px-2 py-0.5 text-danger">
              disabled
            </span>
          )}
          {failoverRank !== undefined && (
            <span className="text-muted-foreground/60">#{failoverRank}</span>
          )}
          <ChevronDown
            className={`ml-auto size-3.5 shrink-0 text-muted-foreground transition-transform ${
              isExpanded ? "rotate-180" : ""
            }`}
            aria-hidden
          />
        </button>
        {typeof result === "object" &&
          (result.ok ? (
            <span className="flex items-center gap-1 text-primary">
              <Check className="size-3.5" aria-hidden />
              {result.latency_ms} ms
            </span>
          ) : (
            <span
              className="flex items-center gap-1 text-danger"
              title={result.error ?? ""}
            >
              <X className="size-3.5" aria-hidden />
              failed
            </span>
          ))}
        {result === "testing" && (
          <Loader2
            className="size-3.5 animate-spin text-muted-foreground"
            aria-hidden
          />
        )}
        <button
          type="button"
          onClick={onRefreshModels}
          disabled={fetchingModels}
          title="Refresh model list"
          className="rounded-lg border border-border p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
          aria-label={`Refresh models for ${row.name}`}
        >
          {fetchingModels ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <RefreshCw className="size-3.5" aria-hidden />
          )}
        </button>
        <button
          type="button"
          onClick={onTest}
          disabled={result === "testing"}
          className="rounded-lg border border-border px-2 py-1 font-medium transition-colors hover:bg-muted disabled:opacity-50"
          aria-label={`Test ${row.name} connection`}
        >
          Test
        </button>
        <span className="flex shrink-0 flex-col">
          <button
            type="button"
            onClick={() => onMove(-1)}
            disabled={busy || isFirst}
            aria-label={`Move ${row.name} up in failover order`}
            className="rounded-t-md border border-border px-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30"
          >
            <ChevronUp className="size-3" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => onMove(1)}
            disabled={busy || isLast}
            aria-label={`Move ${row.name} down in failover order`}
            className="rounded-b-md border border-border px-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30"
          >
            <ChevronDown className="size-3" aria-hidden />
          </button>
        </span>
        <label
          className="flex shrink-0 items-center gap-1 text-muted-foreground"
          title="Included in the failover plan"
        >
          <input
            type="checkbox"
            checked={row.override?.enabled ?? true}
            disabled={busy}
            onChange={(e) => onSetEnabled(e.target.checked)}
            aria-label={`Enable ${row.name}`}
          />
        </label>
      </div>
      {children}
    </li>
  );
}

/** Credential-status dot: filled = saved here, half = from the environment,
 * outline = not configured. */
function KeyDot({ row }: { row: ProviderRow }) {
  const source = row.apiKey?.set
    ? row.apiKey.source
    : row.baseUrl?.set
      ? row.baseUrl.source
      : null;
  return (
    <span
      aria-label={
        source === "db"
          ? "key saved in app"
          : source === "env"
            ? "key from environment"
            : "no key"
      }
      title={
        source === "db"
          ? "Key saved in the app (encrypted)"
          : source === "env"
            ? "Key from the server environment"
            : "No key set"
      }
      className={`inline-block size-2 shrink-0 rounded-full ${
        source === "db"
          ? "bg-primary"
          : source === "env"
            ? "bg-muted-foreground/50"
            : "border border-border"
      }`}
    />
  );
}
