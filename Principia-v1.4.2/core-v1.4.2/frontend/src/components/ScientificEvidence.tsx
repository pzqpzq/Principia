import { useState } from "react";
import { ReceiptFields, ReceiptValue, humanLabel } from "./ReceiptFields";
import { ScientificText } from "./ScientificText";

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
const text = (value: unknown) => typeof value === "string" ? value : "";
const technicalEstimate = /^(?:equation_parameters|parameters|coefficients|standardized_coefficients|feature_names|intercept|ridge|scaler_.*|[bcmsp]_?\d*)$/;

export function CalibrationDetails({ display, original }: { display: RecordValue; original: unknown }) {
  const [exact, setExact] = useState(false);
  const coefficients = Object.entries(record(display.coefficients));
  const count = Number(display.fitted_coefficient_count ?? 0);
  return <details className="scientific-law-audit calibration-details"><summary>Calibration{count ? ` · ${count} fitted coefficients` : " and parameter definitions"}</summary>
    <p>Coefficients are estimated from development data. Normalization constants and search settings are listed separately; they are not identified physical constants.</p>
    {coefficients.length ? <dl className="calibration-coefficients">{coefficients.map(([symbol, value]) => <div key={symbol}><dt><ScientificText value={`$${symbol}$`} /></dt><dd><ReceiptValue value={value} /></dd></div>)}</dl> : null}
    {Object.keys(record(display.normalization)).length ? <details><summary>Normalization and unit references</summary><ReceiptFields value={display.normalization} /></details> : null}
    <details><summary>Complete calibration record</summary><label className="precision-toggle"><input type="checkbox" checked={exact} onChange={event => setExact(event.target.checked)} />Show full stored precision</label><ReceiptFields value={original} exact={exact} /></details>
  </details>;
}

export function ComputedEvidence({ test }: { test: RecordValue }) {
  const [exact, setExact] = useState(false);
  const estimate = record(test.estimate);
  const measurements = Object.fromEntries(Object.entries(estimate).filter(([key]) => !technicalEstimate.test(key)));
  return <article className="data-test-receipt"><header><strong>{humanLabel(text(record(test.analysis_plan).operator) || "Scientific test")}</strong><span>{humanLabel(text(test.state))}</span></header>
    <dl className="data-test-summary"><div><dt>Sample</dt><dd>{text(test.sample_definition) || "Not recorded"}</dd></div><div><dt>Independent units</dt><dd>{Number(test.independent_unit_count ?? 0).toLocaleString()}</dd></div></dl>
    {text(test.expression_latex) ? <div className="data-test-equation"><ScientificText value={`$$${text(test.expression_latex)}$$`} /></div> : null}
    {Object.keys(measurements).length ? <><h4>Measurements</h4><ReceiptFields value={measurements} /></> : null}
    <details><summary>Uncertainty and calibration</summary><ReceiptFields value={{ uncertainty: test.uncertainty, calibration: Object.fromEntries(Object.entries(estimate).filter(([key]) => technicalEstimate.test(key))) }} /></details>
    <details><summary>Complete executed receipt</summary><label className="precision-toggle"><input type="checkbox" checked={exact} onChange={event => setExact(event.target.checked)} />Show full stored precision</label><ReceiptFields value={{ estimate: test.estimate, uncertainty: test.uncertainty, test_id: test.test_id, plan_digest: test.plan_digest, result_digest: test.result_digest, diagnostics: test.diagnostics, split_validation: test.split_validation }} exact={exact} /></details>
  </article>;
}
