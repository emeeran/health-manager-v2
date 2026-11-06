import { Loader2, Search, ShieldAlert, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { InteractionCard } from "../../components/ai-tools/drug-interactions-view";
import { AiToolPage } from "../../components/ai-tools/ai-tool-page";
import {
  checkPairInteraction,
  type PairInteractionResponse,
} from "../../lib/api/drug-interactions";
import { searchDrugs } from "../../lib/api/drugs";
import { listMedications } from "../../lib/api/medications";

const inputClass =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring";

/**
 * Interaction check for ANY two user-named medicines (they need not be in
 * the member's record). Inputs suggest names from the member's medications
 * and the Jan Aushadhi catalog.
 */
export default function DrugInteractionPairPage() {
  return (
    <AiToolPage title="Interaction report — any two medicines">
      {(memberId) => <PairTool memberId={memberId} />}
    </AiToolPage>
  );
}

function PairTool({ memberId }: { memberId: string }) {
  const [medicineA, setMedicineA] = useState("");
  const [medicineB, setMedicineB] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PairInteractionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const interactions = result?.interactions ?? null;
  const providerUsed = result?.provider_used ?? null;

  async function handleCheck() {
    const a = medicineA.trim();
    const b = medicineB.trim();
    if (!a || !b || running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await checkPairInteraction(memberId, a, b));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Interaction check failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-xl border border-border bg-card p-5 shadow-sm">
        <MedicineInput
          label="Medicine A"
          value={medicineA}
          onChange={setMedicineA}
          memberId={memberId}
        />
        <MedicineInput
          label="Medicine B"
          value={medicineB}
          onChange={setMedicineB}
          memberId={memberId}
        />
        <button
          type="button"
          onClick={() => void handleCheck()}
          disabled={running || !medicineA.trim() || !medicineB.trim()}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Search className="size-4" aria-hidden />
          )}
          {running ? "Checking…" : "Check interaction"}
        </button>
        {error && (
          <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
      </div>

      {interactions !== null && (
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            {interactions.length > 0 ? (
              <ShieldAlert className="size-5 text-warning" aria-hidden />
            ) : (
              <ShieldCheck className="size-5 text-primary" aria-hidden />
            )}
            <h3 className="text-sm font-semibold">
              {interactions.length > 0
                ? `${interactions.length} interaction${interactions.length > 1 ? "s" : ""} found`
                : "No documented interaction found"}
            </h3>
            {providerUsed && (
              <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                {providerUsed}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            AI estimate — always confirm with a doctor or pharmacist.
          </p>
          <ul className="mt-3 space-y-2">
            {interactions.map((interaction, index) => (
              <InteractionCard
                key={interaction.drugs.join("+") + index}
                interaction={interaction}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Free-text input with suggestions from the member's meds + the catalog. */
function MedicineInput({
  label,
  value,
  onChange,
  memberId,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  memberId: string;
}) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { data: meds } = useSWR(
    ["medications", "names", memberId],
    () => listMedications(memberId, { status: "active" }),
  );

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  function handleChange(next: string) {
    onChange(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (next.trim().length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      const needle = next.trim().toLowerCase();
      const fromMeds = (meds ?? [])
        .map((m) => m.medicine)
        .filter((name) => name.toLowerCase().includes(needle));
      let fromCatalog: string[] = [];
      try {
        const catalog = await searchDrugs(next.trim());
        fromCatalog = catalog.map((row) => row.name);
      } catch {
        // Catalog suggestions are optional — member names still work.
      }
      setSuggestions([...new Set([...fromMeds, ...fromCatalog])].slice(0, 8));
      setShowSuggestions(true);
    }, 300);
  }

  return (
    <div className="relative">
      <label className="mb-1 block text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => setShowSuggestions(suggestions.length > 0)}
        onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
        placeholder="Type a medicine name"
        className={inputClass}
      />
      {showSuggestions && suggestions.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card shadow-md">
          {suggestions.map((suggestion) => (
            <li key={suggestion}>
              <button
                type="button"
                onMouseDown={() => {
                  onChange(suggestion);
                  setShowSuggestions(false);
                }}
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-muted"
              >
                {suggestion}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
