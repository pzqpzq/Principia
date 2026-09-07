import { useState } from "react";
import { ScientificText } from "./ScientificText";
import { scientificNumber } from "../utils/scientificNumbers";

type RecordValue = Record<string, unknown>;
const object = (value: unknown): value is RecordValue =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const technical = /(?:^|_)(?:id|ids|digest|sha256|version)$|^(?:relative_path|code|equation_ast|assignments)$/;
export const humanLabel = (value: string): string => value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase())
  .replace(/\b(?:Dicom|Nrmse|Rmse|Cv|Ast|Uid|Api)\b/g, token => token.toUpperCase())
  .replace(/\bMm\b/g, "(mm)");

export function ReceiptValue({ value, exact = false }: { value: unknown; exact?: boolean }) {
  if (value === null || value === undefined || value === "") return <span className="data-receipt-empty">Not recorded</span>;
  if (typeof value === "number") {
    const displayed = scientificNumber(value, exact);
    return <span className="receipt-number" title={String(value)}>{/[eE][+-]?\d+$/.test(displayed) ? <ScientificText value={`$${displayed}$`} exact={exact} /> : displayed}</span>;
  }
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  if (Array.isArray(value)) return <ReceiptList values={value} exact={exact} />;
  if (object(value)) return <ReceiptFields value={value} exact={exact} />;
  return <ScientificText value={String(value)} exact={exact} />;
}

function ReceiptList({ values, exact }: { values: unknown[]; exact: boolean }) {
  const [limit, setLimit] = useState(12);
  if (!values.length) return <span className="data-receipt-empty">None recorded</span>;
  if (values.length <= 8 && values.every(value => typeof value === "number"))
    return <span className="receipt-vector" title={values.join(", ")}>[{values.map(value => scientificNumber(Number(value), exact)).join(", ")}]</span>;
  const objects = values.every(object);
  const columns = objects ? [...new Set(values.flatMap(value => Object.keys(value)))]: [];
  const table = objects && columns.length > 0 && columns.length <= 8 && values.every(value => Object.values(value).every(cell => !object(cell) && !Array.isArray(cell)));
  return <div className="receipt-list">
    {table ? <div className="receipt-table-scroll" tabIndex={0} role="region" aria-label="Evidence table"><table><thead><tr>{columns.map(key => <th key={key}>{humanLabel(key)}</th>)}</tr></thead><tbody>{values.slice(0, limit).map((value, index) => <tr key={index}>{columns.map(key => <td key={key}><ReceiptValue value={(value as RecordValue)[key]} exact={exact} /></td>)}</tr>)}</tbody></table></div>
      : <ol>{values.slice(0, limit).map((value, index) => <li key={index}><ReceiptValue value={value} exact={exact} /></li>)}</ol>}
    {values.length > 12 ? <div className="receipt-pagination"><span>{Math.min(limit, values.length)} of {values.length.toLocaleString()} entries</span>{values.length > limit ? <button onClick={() => setLimit(limit + 24)}>Show more entries</button> : null}{limit > 12 ? <button onClick={() => setLimit(12)}>Show fewer</button> : null}</div> : null}
  </div>;
}

export function ReceiptFields({ value, showTechnical = false, exact = false }: { value: unknown; showTechnical?: boolean; exact?: boolean }) {
  if (!object(value)) return <ReceiptValue value={value} exact={exact} />;
  const entries = Object.entries(value).filter(([, item]) => item !== "" && item !== null && item !== undefined);
  if (!entries.length) return <p className="data-receipt-empty">Not recorded</p>;
  const fields = showTechnical ? entries : entries.filter(([key]) => !technical.test(key));
  const provenance = showTechnical ? [] : entries.filter(([key]) => technical.test(key));
  return <div className="receipt-fields-group">
    {fields.length ? <dl className="data-receipt-fields">{fields.map(([key, item]) => <div key={key} className={object(item) || Array.isArray(item) ? "receipt-nested" : ""}><dt>{humanLabel(key)}</dt><dd><ReceiptValue value={item} exact={exact} /></dd></div>)}</dl> : null}
    {provenance.length ? <details className="receipt-technical"><summary>Identifiers and provenance · {provenance.length}</summary><ReceiptFields value={Object.fromEntries(provenance)} showTechnical exact={exact} /></details> : null}
  </div>;
}

export function SourceEvidence({ evidence }: { evidence: RecordValue[] }) {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(12);
  const assetCount = new Set(evidence.map(item => item.asset_id).filter(Boolean)).size;
  const filtered = evidence.filter(item => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  if (!evidence.length) return <p>No source evidence is linked.</p>;
  return <section className="data-receipt-section source-evidence">
    <h3>Source evidence</h3>
    <p>{evidence.length.toLocaleString()} evidence {evidence.length === 1 ? "anchor" : "anchors"} across {assetCount.toLocaleString()} source {assetCount === 1 ? "file" : "files"}. Open a source to inspect its exact location, units and verification receipt.</p>
    <details><summary>Inspect source files and provenance</summary>
      {evidence.length > 6 ? <input aria-label="Search source evidence" placeholder="Search by file, series or identifier…" value={query} onChange={event => { setQuery(event.target.value); setLimit(12); }} /> : null}
      <div className="source-evidence-list">{filtered.slice(0, limit).map((item, index) => {
        const locator = object(item.locator) ? item.locator : {};
        const path = String(locator.relative_path ?? "");
        const title = String(locator.role ?? locator.series ?? (path.split("/").pop() || "Source evidence"));
        return <details key={String(item.evidence_id ?? index)} className="data-evidence-receipt"><summary><strong>{title}</strong><small>{path.split("/").pop() || `Evidence ${index + 1}`}</small></summary>
          <ReceiptFields value={locator} />
          {object(item.units) && Object.keys(item.units).length ? <><h4>Units</h4><ReceiptFields value={item.units} /></> : null}
          <details className="receipt-technical"><summary>Verification receipt</summary><ReceiptFields value={Object.fromEntries(Object.entries(item).filter(([key]) => !["locator", "units"].includes(key)))} showTechnical /></details>
        </details>;
      })}</div>
      {!filtered.length ? <p>No matching source evidence.</p> : null}
      <div className="receipt-pagination"><span>{Math.min(limit, filtered.length)} of {filtered.length} sources shown</span>{filtered.length > limit ? <button onClick={() => setLimit(limit + 24)}>Show more sources</button> : null}</div>
    </details>
  </section>;
}
