import { Trash2 } from "lucide-react";
import { useState } from "react";
import { deleteProviderKey, setProviderKey } from "../../lib/api/household";
import type { AiProviderConfig } from "../../lib/types/household";
import { errorMessage } from "../../lib/utils";
import type { ProviderRow } from "./provider-row";

const inputClass =
  "w-full rounded-lg border border-input bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring";

interface ProviderDetailsProps {
  row: ProviderRow;
  /** Fetched live catalogue, or the static fallback suggestions. */
  models: string[];
  onPatchOverride: (patch: Partial<AiProviderConfig>) => void;
  onRemoveOverride: () => void;
}

/** Inline details for one provider: key, base URL, model override. */
export function ProviderDetails({
  row,
  models,
  onPatchOverride,
  onRemoveOverride,
}: ProviderDetailsProps) {
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
        errorMessage(err, "Could not save key."),
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
        errorMessage(err, "Could not save URL."),
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
