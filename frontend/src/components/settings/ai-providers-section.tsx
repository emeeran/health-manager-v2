import {
  Bot,
  Check,
  ChevronDown,
  Globe2,
  Loader2,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import {
  deleteProviderKey,
  getAiConfig,
  getWebFactcheckStatus,
  listAiProviders,
  listProviderKeys,
  listProviderModels,
  putAiConfig,
  setProviderKey,
  testAiProvider,
} from "../../lib/api/household";
import type {
  AiConfig,
  AiProviderConfig,
  AiProviderTestResult,
  ProviderKeyStatus,
  WebFactcheckStatus,
} from "../../lib/types/household";

/** Known provider names — the board shows one row per provider. */
const PROVIDER_NAMES = [
  "openai",
  "groq",
  "gemini",
  "cohere",
  "deepseek",
  "mistral",
  "openrouter",
  "huggingface",
  "ollama",
] as const;

/** Model suggestions are never hardcoded — providers rotate model names
 * (Groq retired the shipped default within months), so the picker shows
 * only the live catalogue fetched per key via the row's Refresh button. */

/** One merged row of the board: failover entry, stored credentials and the
 * household override for a single provider. */
interface ProviderRow {
  name: string;
  failover?: { model: string; local: boolean };
  override?: AiProviderConfig;
  apiKey?: ProviderKeyStatus;
  baseUrl?: ProviderKeyStatus;
}

const inputClass =
  "w-full rounded-lg border border-input bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring";

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
  const [testResults, setTestResults] = useState<
    Record<string, AiProviderTestResult | "testing">
  >({});
  // Live model catalogues fetched via the row's Refresh button — the only
  // source of picker suggestions, so stale names can never resurface.
  const [modelLists, setModelLists] = useState<Record<string, string[]>>({});
  const [fetchingModels, setFetchingModels] = useState<Record<string, boolean>>(
    {},
  );
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!config || !failover || !keysData) return null;
  const cfg = config;

  const keys: ProviderKeyStatus[] = keysData.keys;

  function findKey(name: string): ProviderKeyStatus | undefined {
    return keys.find((k) => k.name === name);
  }

  const rows: ProviderRow[] = [
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
        err instanceof Error ? err.message : "Could not save AI config.",
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

  async function test(name: string) {
    setError(null);
    setTestResults((r) => ({ ...r, [name]: "testing" }));
    try {
      const result = await testAiProvider(name);
      setTestResults((r) => ({ ...r, [name]: result }));
      await mutateFailover();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed.");
      setTestResults((r) => {
        const rest = { ...r };
        delete rest[name];
        return rest;
      });
    }
  }

  async function refreshModels(name: string) {
    setError(null);
    setFetchingModels((f) => ({ ...f, [name]: true }));
    setExpanded(name); // surface the picker the fresh list feeds
    try {
      const { models } = await listProviderModels(name);
      setModelLists((lists) => ({ ...lists, [name]: models }));
      // Purge a persisted override the key's catalogue no longer serves —
      // the row falls back to the server default instead of failing every
      // request with a decommissioned model name.
      const override = cfg.providers.find((p) => p.name === name);
      if (override?.model && !models.includes(override.model)) {
        void patchOverride(name, { model: null });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Model refresh failed.");
    } finally {
      setFetchingModels((f) => {
        const rest = { ...f };
        delete rest[name];
        return rest;
      });
    }
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
            setTestResults({});
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
          const result = testResults[row.name];
          const isExpanded = expanded === row.name;
          return (
            <li key={row.name} data-testid={`provider-row-${row.name}`}>
              <div
                className={`flex flex-wrap items-center gap-2 px-3 py-2 text-xs ${
                  isExpanded ? "bg-muted/30" : ""
                }`}
              >
                <KeyDot row={row} />
                <button
                  type="button"
                  onClick={() => setExpanded(isExpanded ? null : row.name)}
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
                  {row.failover && (
                    <span className="text-muted-foreground/60">
                      #
                      {failover.providers.findIndex(
                        (p) => p.name === row.name,
                      ) + 1}
                    </span>
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
                  onClick={() => void refreshModels(row.name)}
                  disabled={fetchingModels[row.name]}
                  title="Refresh model list"
                  className="rounded-lg border border-border p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
                  aria-label={`Refresh models for ${row.name}`}
                >
                  {fetchingModels[row.name] ? (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden />
                  ) : (
                    <RefreshCw className="size-3.5" aria-hidden />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => void test(row.name)}
                  disabled={result === "testing"}
                  className="rounded-lg border border-border px-2 py-1 font-medium transition-colors hover:bg-muted disabled:opacity-50"
                  aria-label={`Test ${row.name} connection`}
                >
                  Test
                </button>
              </div>
              {isExpanded && (
                <ProviderDetails
                  row={row}
                  busy={busy}
                  models={modelLists[row.name] ?? []}
                  onPatchOverride={(patch) =>
                    void patchOverride(row.name, patch)
                  }
                  onRemoveOverride={() => void removeOverride(row.name)}
                />
              )}
            </li>
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

/** Inline details for one provider: key, base URL, model override. */
function ProviderDetails({
  row,
  busy,
  models,
  onPatchOverride,
  onRemoveOverride,
}: {
  row: ProviderRow;
  busy: boolean;
  /** Fetched live catalogue, or the static fallback suggestions. */
  models: string[];
  onPatchOverride: (patch: Partial<AiProviderConfig>) => void;
  onRemoveOverride: () => void;
}) {
  const [keyDraft, setKeyDraft] = useState("");
  const [keyBusy, setKeyBusy] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const baseUrlKey = `${row.name.toUpperCase()}_BASE_URL`;
  const [urlDraft, setUrlDraft] = useState<string | null>(null);
  const [modelDraft, setModelDraft] = useState<string | null>(null);

  async function saveKey() {
    if (!keyDraft) return;
    setKeyBusy(true);
    setDetailError(null);
    try {
      await setProviderKey(`${row.name.toUpperCase()}_API_KEY`, keyDraft);
      setKeyDraft("");
    } catch (err) {
      setDetailError(
        err instanceof Error ? err.message : "Could not save key.",
      );
    } finally {
      setKeyBusy(false);
    }
  }

  async function saveUrl() {
    if (urlDraft === null) return;
    setDetailError(null);
    try {
      await setProviderKey(baseUrlKey, urlDraft.trim());
      setUrlDraft(null);
    } catch (err) {
      setDetailError(
        err instanceof Error ? err.message : "Could not save URL.",
      );
    }
  }

  return (
    <div className="space-y-2.5 border-t border-border/60 px-3 py-3">
      {row.apiKey && (
        <div className="flex items-center gap-2">
          <span className="w-24 shrink-0 font-mono text-xs text-muted-foreground">
            API key
          </span>
          <input
            type="password"
            value={keyDraft}
            onChange={(e) => setKeyDraft(e.target.value)}
            placeholder={
              row.apiKey.set ? (row.apiKey.value ?? "set") : "not set"
            }
            autoComplete="off"
            aria-label={`API key for ${row.name}`}
            className={inputClass}
          />
          <button
            type="button"
            onClick={() => void saveKey()}
            disabled={keyBusy || !keyDraft}
            className="shrink-0 rounded-lg bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            {keyBusy ? "…" : "Save key"}
          </button>
          {row.apiKey.source === "db" && (
            <button
              type="button"
              aria-label={`Remove saved ${row.apiKey.name}`}
              onClick={() =>
                void deleteProviderKey(row.apiKey!.name).catch(() =>
                  setDetailError("Could not remove key."),
                )
              }
              className="shrink-0 rounded-lg p-1.5 text-danger transition-colors hover:bg-danger/10"
            >
              <Trash2 className="size-3.5" aria-hidden />
            </button>
          )}
        </div>
      )}

      {row.baseUrl && (
        <div className="flex items-center gap-2">
          <label className="w-24 shrink-0 font-mono text-xs text-muted-foreground">
            {row.baseUrl.name.replace(/_(BASE_URL)/, " base URL")}
          </label>
          <input
            value={urlDraft ?? row.baseUrl.value ?? ""}
            onChange={(e) => setUrlDraft(e.target.value)}
            placeholder="default endpoint"
            aria-label={`${row.baseUrl.name}`}
            className={inputClass}
          />
          {urlDraft !== null && (
            <button
              type="button"
              onClick={() => void saveUrl()}
              className="shrink-0 rounded-lg bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground"
            >
              Save URL
            </button>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="w-24 shrink-0 font-mono text-xs text-muted-foreground">
          Model
        </span>
        <input
          value={modelDraft ?? row.override?.model ?? ""}
          onChange={(e) => {
            const value = e.target.value;
            setModelDraft(value);
            // Picking a listed model persists right away; free text waits
            // for blur so typing isn't saved mid-word.
            if (
              models.includes(value) &&
              value !== (row.override?.model ?? "")
            ) {
              onPatchOverride({ model: value });
              setModelDraft(null);
            }
          }}
          onBlur={() => {
            if (
              modelDraft !== null &&
              modelDraft !== (row.override?.model ?? "")
            ) {
              onPatchOverride(
                modelDraft.trim()
                  ? { model: modelDraft.trim() }
                  : { model: null },
              );
            }
            setModelDraft(null);
          }}
          placeholder="server default"
          list={`models-${row.name}`}
          aria-label={`Model override for ${row.name}`}
          className={inputClass}
        />
        <datalist id={`models-${row.name}`}>
          {models.map((model) => (
            <option key={model} value={model} />
          ))}
        </datalist>
        {row.override ? (
          <>
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={row.override.enabled}
                onChange={(e) => onPatchOverride({ enabled: e.target.checked })}
                disabled={busy}
              />
              enabled
            </label>
            <button
              type="button"
              onClick={onRemoveOverride}
              className="rounded-lg border border-border px-2 py-1 text-xs text-danger transition-colors hover:bg-danger/10"
            >
              Remove override
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => onPatchOverride({ enabled: true })}
            className="rounded-lg border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Add override
          </button>
        )}
      </div>

      {detailError && (
        <p role="alert" className="text-xs text-danger">
          {detailError}
        </p>
      )}
    </div>
  );
}
