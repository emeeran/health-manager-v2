import { Loader2, Pill, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { AiToolPage } from "../../components/ai-tools/ai-tool-page";
import { getDrugInfo, searchDrugs, type DrugInfo } from "../../lib/api/drugs";

const inputClass =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring";

const SOURCE_LABELS: Record<DrugInfo["source"], string> = {
  openfda: "openFDA",
  rxnorm: "RxNorm (NIH)",
  ai: "AI estimate",
  unavailable: "Not found",
};

/**
 * Complete info on a medicine: authenticated lookup (openFDA → RxNorm → AI
 * fallback), rendered as structured sections with the source named.
 */
export default function DrugInfoPage() {
  return (
    <AiToolPage title="Medicine information">
      {(memberId) => <DrugInfoTool memberId={memberId} />}
    </AiToolPage>
  );
}

function DrugInfoTool({ memberId }: { memberId: string }) {
  const [query, setQuery] = useState("");
  const [running, setRunning] = useState(false);
  const [info, setInfo] = useState<DrugInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleLookup(name?: string) {
    const medicine = (name ?? query).trim();
    if (!medicine || running) return;
    setQuery(medicine);
    setRunning(true);
    setError(null);
    setInfo(null);
    try {
      setInfo(await getDrugInfo(memberId, medicine));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-xl border border-border bg-card p-5 shadow-sm">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleLookup();
          }}
          className="space-y-2"
        >
          <label className="block text-xs font-medium text-muted-foreground">
            Medicine name
          </label>
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Metformin"
              className={inputClass}
            />
            <button
              type="submit"
              disabled={running || !query.trim()}
              className="flex shrink-0 items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {running ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <Search className="size-4" aria-hidden />
              )}
              Look up
            </button>
          </div>
          {query.trim().length >= 2 && (
            <SuggestionRow query={query} onPick={(name) => void handleLookup(name)} />
          )}
        </form>
        {error && (
          <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
      </div>

      {info && (
        <div className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Pill className="size-4 text-muted-foreground" aria-hidden />
            <h3 className="text-sm font-semibold">
              {info.brand ?? info.generic ?? "No information found"}
            </h3>
            <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
              Source: {SOURCE_LABELS[info.source]}
            </span>
          </div>
          <dl className="space-y-2 text-sm">
            <InfoRow label="Generic name" value={info.generic} />
            <InfoRow label="Brand name" value={info.brand} />
            <InfoRow label="Manufacturer" value={info.manufacturer} />
            <InfoRow label="Active ingredients" value={info.ingredients} />
          </dl>
          <p className="text-xs text-muted-foreground">
            Registry/AI summary — not medical advice; confirm with a doctor or
            pharmacist.
          </p>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div>
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function SuggestionRow({
  query,
  onPick,
}: {
  query: string;
  onPick: (name: string) => void;
}) {
  const [names, setNames] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    searchDrugs(query.trim())
      .then((rows) => {
        if (!cancelled) {
          setNames([...new Set(rows.map((r) => r.name))].slice(0, 6));
        }
      })
      .catch(() => {
        if (!cancelled) setNames([]);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  if (!names.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {names.map((name) => (
        <button
          key={name}
          type="button"
          onClick={() => onPick(name)}
          className="rounded-full border border-border bg-background px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {name}
        </button>
      ))}
    </div>
  );
}
