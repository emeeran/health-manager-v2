import { Fragment } from "react";
import { Markdown } from "../shared/markdown";

/** Clinical data sections that render as labelled rows when present. */
const CLINICAL_SECTIONS = [
  "medications",
  "imaging",
  "screenings",
  "labs",
  "vitals",
  "advice",
] as const;

export function ClinicalDataView({ data }: { data: Record<string, unknown> }) {
  if (Object.keys(data).length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No structured clinical data was extracted.
      </p>
    );
  }

  // Every section — scalar, object, or list — becomes one labelled row in a
  // single dl, matching the record-detail field layout (label left, content
  // flowing right). Free-text an extractor mis-filed inside an object
  // section (diet advice under medications…) is split into its own advice
  // row so each section stays one kind of content.
  const rawRows: [string, unknown][] = [
    ...Object.entries(data).filter(
      ([key, value]) =>
        key !== "consolidated_report" &&
        (!(CLINICAL_SECTIONS as readonly string[]).includes(key) ||
          !Array.isArray(value)),
    ),
    ...CLINICAL_SECTIONS.filter((key) => Array.isArray(data[key])).map(
      (key) => [key, data[key]] as [string, unknown],
    ),
  ];
  const rows: [string, unknown][] = [];
  const advice: string[] = [];
  for (const [key, value] of rawRows) {
    if (
      Array.isArray(value) &&
      key !== "advice" &&
      value.some((item) => typeof item === "string")
    ) {
      const objects = value.filter(
        (item) => typeof item === "object" && item !== null,
      );
      const strings = value.filter(
        (item) => typeof item === "string" && item,
      );
      if (objects.length > 0) rows.push([key, objects]);
      advice.push(...strings.map(String));
    } else {
      rows.push([key, value]);
    }
  }
  if (advice.length > 0 && !rows.some(([key]) => key === "advice")) {
    rows.push(["advice", advice]);
  }
  const report =
    typeof data.consolidated_report === "string"
      ? data.consolidated_report
      : null;

  return (
    <div className="space-y-3">
      {report && (
        <div className="rounded-xl border border-border bg-background p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Consolidated clinical report
          </p>
          <div className="mt-2">
            <Markdown>{report}</Markdown>
          </div>
        </div>
      )}

      <dl className="divide-y divide-border">
        {rows.map(([key, value]) => (
          <div key={key} className="flex gap-3 py-2 first:pt-0 last:pb-0">
            <dt className="w-40 shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {titleize(key)}
            </dt>
            <dd className="min-w-0 flex-1 text-sm">
              {Array.isArray(value) ? (
                <ItemsList items={value} />
              ) : typeof value === "object" && value !== null ? (
                <span className="leading-snug">
                  {Object.entries(value)
                    .filter(([, v]) => isPresent(v))
                    .map(([k, v], index) => (
                      <Fragment key={k}>
                        {index > 0 && (
                          <span
                            aria-hidden
                            className="text-muted-foreground/60"
                          >
                            {" · "}
                          </span>
                        )}
                        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                          {titleize(k)}
                        </span>{" "}
                        <span>{formatValue(v)}</span>
                      </Fragment>
                    ))}
                </span>
              ) : (
                formatValue(value)
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Right-column content for a list section: bullet lines for free-text
 * advice, a compact table for structured entries (medications, labs…). */
function ItemsList({ items }: { items: unknown[] }) {
  const allPlain = items.every(
    (item) => typeof item !== "object" || item === null,
  );
  if (allPlain) {
    return (
      <ul className="space-y-0.5">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2 leading-snug">
            <span aria-hidden className="mt-[0.45em] size-1 shrink-0 rounded-full bg-muted-foreground/60" />
            <span className="min-w-0">{formatValue(item)}</span>
          </li>
        ))}
      </ul>
    );
  }
  const objects = items.filter(
    (item): item is Record<string, unknown> =>
      typeof item === "object" && item !== null,
  );
  return <ObjectsTable items={objects} />;
}

/** Flattened, compact table for a structured section: one column per field
 * (union across entries), the identity field first in bold. Columns whose
 * every value is empty are dropped. */
function ObjectsTable({ items }: { items: Record<string, unknown>[] }) {
  const first = items[0] ?? {};
  const titleKey = itemTitleKey(first);
  const columnSet = new Set<string>();
  for (const item of items) {
    for (const key of Object.keys(item)) {
      if (!HIDDEN_ITEM_KEYS.has(key) && key !== titleKey) columnSet.add(key);
    }
  }
  const columns = [...columnSet].filter((key) =>
    items.some((item) => isPresent(item[key])),
  );

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-border text-left">
          {titleKey && (
            <th className="py-1 pr-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {titleize(titleKey)}
            </th>
          )}
          {columns.map((key) => (
            <th
              key={key}
              className="py-1 pr-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
            >
              {titleize(key)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-border/60">
        {items.map((item, index) => (
          <tr key={index}>
            {titleKey && (
              <td className="py-1 pr-3 align-top font-medium">
                {titleKey in item ? formatValue(item[titleKey]) : ""}
              </td>
            )}
            {columns.map((key) => (
              <td key={key} className="py-1 pr-3 align-top leading-snug">
                {isPresent(item[key]) ? formatValue(item[key]) : ""}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function titleize(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Fields used as the headline of an extracted item card, in priority order. */
const ITEM_TITLE_KEYS = [
  "name",
  "type",
  "modality",
  "test",
  "panel",
  "investigation",
] as const;

/**
 * Fields hidden from the detail grid because they are either already shown
 * as the card headline or pure noise (extraction provenance).
 */
const HIDDEN_ITEM_KEYS = new Set(["id", "record_id", "source"]);

function isPresent(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

function itemTitleKey(item: Record<string, unknown>): string | null {
  for (const key of ITEM_TITLE_KEYS) {
    if (typeof item[key] === "string" && item[key]) return key;
  }
  const first = Object.entries(item).find(
    ([, value]) => typeof value === "string" && value,
  );
  return first ? first[0] : null;
}
