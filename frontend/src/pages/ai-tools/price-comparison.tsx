import { Loader2, Plus, Printer, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { AiToolPage } from "../../components/ai-tools/ai-tool-page";
import {
  compareDrugPrices,
  type PriceCompareResponse,
} from "../../lib/api/drugs";
import { listMedications } from "../../lib/api/medications";
import { downloadCsv } from "../../lib/export";

const inputClass =
  "rounded-lg border border-input bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring";

/**
 * Price comparison over the Jan Aushadhi catalog: the table is computed in
 * code (catalog MRP — never a model claim); the optional AI narrative is
 * grounded in the table only. Printable + CSV-exportable.
 */
export default function PriceComparisonPage() {
  return (
    <AiToolPage title="Price comparison">
      {(memberId) => <PriceTool memberId={memberId} />}
    </AiToolPage>
  );
}

function PriceTool({ memberId }: { memberId: string }) {
  const [editedNames, setEditedNames] = useState<string[] | null>(null);
  const [draft, setDraft] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PriceCompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Pre-fill with the member's active medicines (names only).
  const { data: meds } = useSWRMeds(memberId);
  const prefilled = useMemo(
    () =>
      meds?.length
        ? [...new Set(meds.map((m) => m.medicine).filter(Boolean))].slice(0, 15)
        : null,
    [meds],
  );
  // User edits win over the pre-fill once made.
  const names = editedNames ?? prefilled ?? [];

  function addDraft() {
    const value = draft.trim();
    if (!value) return;
    if (names.length < 15) setEditedNames([...new Set([...names, value])]);
    setDraft("");
    setResult(null);
  }

  function removeName(name: string) {
    setEditedNames(names.filter((n) => n !== name));
    setResult(null);
  }

  async function handleCompare() {
    if (!names.length || running) return;
    setRunning(true);
    setError(null);
    try {
      setResult(await compareDrugPrices(names, { memberId }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Price comparison failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">
            Medicines to compare (pre-filled from active medications)
          </p>
          <div className="flex flex-wrap gap-1.5">
            {names.map((name) => (
              <span
                key={name}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-0.5 text-xs"
              >
                {name}
                <button
                  type="button"
                  onClick={() => removeName(name)}
                  aria-label={`Remove ${name}`}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3" aria-hidden />
                </button>
              </span>
            ))}
            {!names.length && (
              <span className="text-xs text-muted-foreground">
                Add medicines below.
              </span>
            )}
          </div>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            addDraft();
          }}
          className="flex gap-2"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a medicine name"
            className={`${inputClass} grow`}
          />
          <button
            type="submit"
            disabled={!draft.trim() || names.length >= 15}
            className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-60"
          >
            <Plus className="size-4" aria-hidden />
            Add
          </button>
        </form>
        <button
          type="button"
          onClick={() => void handleCompare()}
          disabled={running || !names.length}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Search className="size-4" aria-hidden />
          )}
          {running ? "Comparing…" : "Compare prices"}
        </button>
        {error && (
          <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
      </div>

      {result && (
        <div className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
            <h3 className="text-sm font-semibold">
              {result.matched_count} of {result.items.length} matched
              {result.total_price !== null && ` · total ₹${result.total_price.toFixed(2)}`}
            </h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => window.print()}
                className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
              >
                <Printer className="size-4" aria-hidden />
                Print / Save PDF
              </button>
              <button
                type="button"
                onClick={() =>
                  downloadCsv(
                    "price-comparison.csv",
                    [
                      ["Medicine", "Catalog name", "Manufacturer", "Ingredients", "Package", "Price (₹)", "Match"],
                      ...result.items.map((item) => [
                        item.medicine,
                        item.catalog_name,
                        item.manufacturer,
                        item.ingredients,
                        item.package,
                        item.price,
                        item.match,
                      ]),
                    ],
                  )
                }
                className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
              >
                CSV
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3">Medicine</th>
                  <th className="py-2 pr-3">Catalog product</th>
                  <th className="py-2 pr-3">Manufacturer</th>
                  <th className="py-2 pr-3">Composition</th>
                  <th className="py-2 pr-3">Pack</th>
                  <th className="py-2 pr-3 text-right">Price (₹)</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((item) => (
                  <tr key={item.medicine} className="border-b border-border/60">
                    <td className="py-2 pr-3">
                      {item.medicine}
                      {!item.match && (
                        <span className="ml-1.5 text-xs text-warning">
                          not matched
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3">{item.catalog_name ?? "—"}</td>
                    <td className="py-2 pr-3">{item.manufacturer ?? "—"}</td>
                    <td className="py-2 pr-3">{item.ingredients ?? "—"}</td>
                    <td className="py-2 pr-3">{item.package ?? "—"}</td>
                    <td className="py-2 pr-3 text-right">
                      {item.price !== null ? item.price.toFixed(2) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {result.narrative && (
            <p className="rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
              {result.narrative}
              {result.provider_used && (
                <span className="ml-1.5 text-xs opacity-70">
                  ({result.provider_used})
                </span>
              )}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Reference prices from the Jan Aushadhi catalog; actual retail
            prices vary.
          </p>
        </div>
      )}
    </div>
  );
}

function useSWRMeds(memberId: string) {
  return useSWR(["medications", "price-prefill", memberId], () =>
    listMedications(memberId, { status: "active" }),
  );
}
