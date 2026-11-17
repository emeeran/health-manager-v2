import { Bot, Globe2, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import {
  getAiConfig,
  getWebFactcheckStatus,
  listAiProviders,
  listProviderKeys,
  putAiConfig,
} from "../../lib/api/household";
import type {
  AiConfig,
  AiProviderConfig,
  ProviderKeyStatus,
  WebFactcheckStatus,
} from "../../lib/types/household";
import { errorMessage } from "../../lib/utils";
import { ProviderDetails } from "./provider-details";
import { ProviderRowView } from "./provider-row";
import type { ProviderRow } from "./provider-row";
import { useProviderDiagnostics } from "./use-provider-diagnostics";

/** Known provider names — the board shows one row per provider. */
const PROVIDER_NAMES = [
  "groq",
  "gemini",
  "zai",
  "deepseek",
  "mistral",
  "openrouter",
  "huggingface",
  "ollama",
] as const;

/** Model suggestions are never hardcoded — providers rotate model names
 * (Groq retired the shipped default within months), so the picker shows
 * only the live catalogue fetched per key via the row's Refresh button. */

/**
 * Per-household AI routing, compacted into one board: a primary select, one
 * row per provider (status dot, model, connection test), and an inline
 * details panel per row holding the key, base URL and model override.
 */
export function AiProvidersSection() {
  const { data: config, mutate: mutateConfig } = useSWR<AiConfig>(
    "/household/ai-config",
    getAiConfig,
  );
  const { data: failover, mutate: mutateFailover } = useSWR<{
    providers: { name: string; model: string; local: boolean }[];
  }>("/system/ai-providers", listAiProviders);
  const { data: keysData } = useSWR("/system/provider-keys", listProviderKeys);
  const { data: factcheck } = useSWR<WebFactcheckStatus>(
    "/system/web-factcheck",
    getWebFactcheckStatus,
  );

  const [expanded, setExpanded] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Function declarations below are hoisted, so this hook can wire
  // patchOverride before the early return — its callbacks only ever run
  // once the data has loaded.
  const {
    testResults,
    modelLists,
    fetchingModels,
    test,
    refreshModels,
    clearTestResults,
  } = useProviderDiagnostics({
    mutateFailover: () => mutateFailover(),
    onRefreshStart: (name) => setExpanded(name),
    getOverrideModel: (name) => config?.providers.find((p) => p.name === name)?.model,
    patchOverride,
    setError,
  });

  if (!config || !failover || !keysData) return null;
  const cfg = config;

  const keys: ProviderKeyStatus[] = keysData.keys;

  function findKey(name: string): ProviderKeyStatus | undefined {
    return keys.find((k) => k.name === name);
  }

  const allRows: ProviderRow[] = [
    ...PROVIDER_NAMES.map((name) => {
      const upper = name.toUpperCase();
      return {
        name,
        failover: failover.providers.find((p) => p.name === name),
        override: cfg.providers.find((p) => p.name === name),
        apiKey: findKey(`${upper}_API_KEY`),
        baseUrl: findKey(`${upper}_BASE_URL`),
      };
    }),
    // Failover entries for providers outside the known list (future names).
    ...failover.providers
      .filter((p) => !(PROVIDER_NAMES as readonly string[]).includes(p.name))
      .map((p) => ({ name: p.name, failover: p })),
  ];

  /** Effective failover ranking: cfg.order ranked names first, the rest in
   * their default order behind them — mirrored from the backend's resolver. */
  const ranked: ProviderRow[] = [
    ...(cfg.order ?? [])
      .map((name) => allRows.find((row) => row.name === name))
      .filter((row): row is ProviderRow => row !== undefined),
    ...allRows.filter((row) => !(cfg.order ?? []).includes(row.name)),
  ];
  const rows = ranked;

  // De-clutter: rows with no credentials, no override and no failover entry
  // stay collapsed until asked for.
  const visible = rows.filter(
    (row) =>
      showAll ||
      row.failover ||
      row.override ||
      row.apiKey?.set ||
      row.baseUrl?.set,
  );
  const hiddenCount = rows.length - visible.length;

  async function saveConfig(next: AiConfig) {
    setBusy(true);
    setError(null);
    try {
      await putAiConfig(next);
      await mutateConfig(next, { revalidate: false });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(
        errorMessage(err, "Could not save AI config."),
      );
      await mutateConfig();
    } finally {
      setBusy(false);
    }
  }

  function patchOverride(name: string, patch: Partial<AiProviderConfig>) {
    const exists = cfg.providers.some((p) => p.name === name);
    const providers = exists
      ? cfg.providers.map((p) => (p.name === name ? { ...p, ...patch } : p))
      : [...cfg.providers, { name, enabled: true, ...patch }];
    return saveConfig({ ...cfg, providers });
  }

  async function removeOverride(name: string) {
    return saveConfig({
      ...cfg,
      providers: cfg.providers.filter((p) => p.name !== name),
    });
  }

  /** Persist the shown ranking as the failover order. */
  function setOrder(next: ProviderRow[]) {
    return saveConfig({
      ...cfg,
      order: next.map((row) => row.name),
    });
  }

  function moveRow(name: string, dir: -1 | 1) {
    const at = ranked.findIndex((row) => row.name === name);
    const to = at + dir;
    if (at === -1 || to < 0 || to >= ranked.length) return;
    const next = [...ranked];
    next.splice(to, 0, next.splice(at, 1)[0]);
    void setOrder(next);
  }

  function setEnabled(name: string, enabled: boolean) {
    void patchOverride(name, { enabled });
  }

  return (
    <section
      aria-label="AI providers"
      className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Bot className="size-4 text-primary" aria-hidden />
          AI providers
        </h2>
        <label className="ml-auto flex items-center gap-2 text-xs font-medium text-muted-foreground">
          Primary
          <select
            value={cfg.primary_provider}
            disabled={busy}
            onChange={(e) =>
              void saveConfig({
                ...cfg,
                primary_provider: e.target
                  .value as AiConfig["primary_provider"],
              })
            }
            className="rounded-lg border border-input bg-background px-2 py-1 text-xs font-normal text-foreground"
          >
            <option value="auto">auto</option>
            <option value="cloud">cloud only</option>
            <option value="local">local only</option>
            {PROVIDER_NAMES.map((name) => (
              <option key={name} value={name}>
                {name} first
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => {
            clearTestResults();
            void mutateFailover();
          }}
          aria-label="Refresh provider list"
          className="rounded-lg border border-border p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <RefreshCw className="size-3.5" aria-hidden />
        </button>
      </div>

      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs">
        <Globe2 className="size-3.5 text-muted-foreground" aria-hidden />
        <span className="font-medium">Web fact-checking</span>
        <span className="text-muted-foreground">
          {factcheck?.enabled && factcheck.configured
            ? `SearXNG configured · up to ${factcheck.max_claims} claims per audit`
            : "Not configured — set WEB_FACTCHECK_ENABLED=true and SEARXNG_URL"}
        </span>
        <span className="text-muted-foreground">
          · members opt in per profile
        </span>
      </p>

      <ul className="divide-y divide-border rounded-lg border border-border">
        {visible.map((row) => {
          const model = row.override?.model || row.failover?.model || null;
          const isExpanded = expanded === row.name;
          return (
            <ProviderRowView
              key={row.name}
              row={row}
              model={model}
              failoverRank={
                row.failover
                  ? failover.providers.findIndex((p) => p.name === row.name) + 1
                  : undefined
              }
              result={testResults[row.name]}
              fetchingModels={fetchingModels[row.name] ?? false}
              busy={busy}
              isExpanded={isExpanded}
              isFirst={row.name === ranked[0]?.name}
              isLast={row.name === ranked[ranked.length - 1]?.name}
              onToggle={() => setExpanded(isExpanded ? null : row.name)}
              onTest={() => void test(row.name)}
              onRefreshModels={() => void refreshModels(row.name)}
              onMove={(dir) => moveRow(row.name, dir)}
              onSetEnabled={(enabled) => setEnabled(row.name, enabled)}
            >
              {isExpanded && (
                <ProviderDetails
                  row={row}
                  models={modelLists[row.name] ?? []}
                  onPatchOverride={(patch) =>
                    void patchOverride(row.name, patch)
                  }
                  onRemoveOverride={() => void removeOverride(row.name)}
                />
              )}
            </ProviderRowView>
          );
        })}
      </ul>

      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          Show {hiddenCount} more provider{hiddenCount > 1 ? "s" : ""}
        </button>
      )}

      {(busy || saved || error) && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          {busy && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
          {saved && <span className="text-primary">Saved.</span>}
          {error && (
            <span role="alert" className="text-danger">
              {error}
            </span>
          )}
        </p>
      )}
    </section>
  );
}
