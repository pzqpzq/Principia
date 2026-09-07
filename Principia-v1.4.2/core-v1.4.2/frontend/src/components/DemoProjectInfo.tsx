import { useState } from "react";
import { FocusDialog } from "./FocusDialog";

export function DemoProjectInfo({ demo }: { demo: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const sources = (Array.isArray(demo.source_access) ? demo.source_access : []) as Array<Record<string, unknown>>;
  return <>
    <button type="button" className="demo-info-button" onClick={() => setOpen(true)}>Dataset & evidence</button>
    {open ? <FocusDialog title="About this public demo" resizable onClose={() => setOpen(false)}>
      <p>{String(demo.description || "A curated discovery from public data.")}</p>
      {demo.editorial_review ? <><h3>Why this example</h3><p>{String(demo.editorial_review)}</p></> : null}
      <p>Equations, recorded tests, study maps, and derived evidence are included. The original raw dataset is not bundled.</p>
      <h3>Public source data</h3>
      <ul>{sources.map((source, index) => <li key={index}>
        {String(source.url || "").startsWith("https://") ? <a href={String(source.url)} target="_blank" rel="noreferrer">{String(source.title || "Open the public dataset")} ↗</a> : <span>{String(source.title || "Public dataset")}</span>}
        {source.license ? <p>{String(source.license)}</p> : null}
      </li>)}</ul>
      <h3>Evidence boundary</h3>
      <p>{String(demo.evidence_boundary || "Recorded evidence is available offline. Reconnect source data to run a new discovery.")}</p>
      <p>These are selected examples. Consult each Rule’s validation scope and limitations before applying it to new measurements.</p>
      <div className="project-dialog-actions"><button onClick={() => setOpen(false)}>Close</button></div>
    </FocusDialog> : null}
  </>;
}
