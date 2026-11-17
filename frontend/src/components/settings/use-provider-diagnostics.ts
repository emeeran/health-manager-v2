import { useState } from "react";
import { listProviderModels, testAiProvider } from "../../lib/api/household";
import type {
  AiProviderConfig,
  AiProviderTestResult,
} from "../../lib/types/household";
import { errorMessage } from "../../lib/utils";

interface ProviderDiagnosticsOptions {
  /** Revalidates the failover board after a live connection test. */
  mutateFailover: () => Promise<unknown>;
  /** Surfaces the model picker a fresh catalogue feeds. */
  onRefreshStart: (name: string) => void;
  /** Current persisted model override for a provider, if any. */
  getOverrideModel: (name: string) => string | null | undefined;
  patchOverride: (name: string, patch: Partial<AiProviderConfig>) => void;
  setError: (message: string | null) => void;
}

/** Connection-test results and live model catalogues for the provider board.
 * All requests go through lib/api — this hook only orchestrates them. */
export function useProviderDiagnostics({
  mutateFailover,
  onRefreshStart,
  getOverrideModel,
  patchOverride,
  setError,
}: ProviderDiagnosticsOptions) {
  const [testResults, setTestResults] = useState<
    Record<string, AiProviderTestResult | "testing">
  >({});
  // Live model catalogues fetched via the row's Refresh button — the only
  // source of picker suggestions, so stale names can never resurface.
  const [modelLists, setModelLists] = useState<Record<string, string[]>>({});
  const [fetchingModels, setFetchingModels] = useState<Record<string, boolean>>(
    {},
  );

  async function test(name: string) {
    setError(null);
    setTestResults((r) => ({ ...r, [name]: "testing" }));
    try {
      const result = await testAiProvider(name);
      setTestResults((r) => ({ ...r, [name]: result }));
      await mutateFailover();
    } catch (err) {
      setError(errorMessage(err, "Test failed."));
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
    onRefreshStart(name);
    try {
      const { models } = await listProviderModels(name);
      setModelLists((lists) => ({ ...lists, [name]: models }));
      // Purge a persisted override the key's catalogue no longer serves —
      // the row falls back to the server default instead of failing every
      // request with a decommissioned model name.
      const overrideModel = getOverrideModel(name);
      if (overrideModel && !models.includes(overrideModel)) {
        void patchOverride(name, { model: null });
      }
    } catch (err) {
      setError(errorMessage(err, "Model refresh failed."));
    } finally {
      setFetchingModels((f) => {
        const rest = { ...f };
        delete rest[name];
        return rest;
      });
    }
  }

  /** Drop all results — used when the board itself is refreshed. */
  function clearTestResults() {
    setTestResults({});
  }

  return {
    testResults,
    modelLists,
    fetchingModels,
    test,
    refreshModels,
    clearTestResults,
  };
}
