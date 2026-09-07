import type { ReactNode } from 'react';
import { FocusDialog } from './FocusDialog';
import { DataDiscoveryPhases } from './DataDiscoveryPhases';
import { ResearchRunStatus, finishedResearchStates } from './ResearchRunStatus';

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value && typeof value === 'object' ? value as RecordValue : {};
const text = (value: unknown) => typeof value === 'string' ? value : '';
export function inventorySize(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Inventory pending';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']; let size = value, unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++; }
  return `${size.toLocaleString(undefined, { maximumFractionDigits: unit ? 1 : 0 })} ${units[unit]}`;
}
export function DiscoveryActivityDialog({ study, sources, counts, cancelling, error, onStop, onClose, onResults, children }: {
  study: RecordValue; sources: { source_id: string; display_name: string; display_location?: string }[]; counts: RecordValue;
  cancelling: boolean; error?: string; onStop: () => void; onClose: () => void; onResults: () => void; children?: ReactNode;
}) {
  const request = record(study.request), coverage = record(study.coverage), job = record(study.job), execution = record(study.execution);
  const resolved = record(coverage.resolved_models), state = text(study.state), complete = finishedResearchStates.has(state);
  const sourceIds = (Array.isArray(study.source_ids) ? study.source_ids : Array.isArray(request.source_ids) ? request.source_ids : []).map(String);
  const inventories = Array.isArray(coverage.sources) ? coverage.sources.map(record) : [];
  const model = (kind: 'reasoning_model' | 'vision_model') => text(resolved[kind]) || (kind === 'reasoning_model' ? text(job.model) : '') || (text(request[kind]) === 'auto' ? 'Auto · awaiting model selection' : text(request[kind])) || 'Auto · awaiting model selection';
  return <FocusDialog title="Discovery activity" resizable onClose={onClose}>
    <div className="discovery-activity">
      <header><div><small>Current discovery task</small><h2>Discovery activity</h2></div><button aria-label="Close discovery activity" title="Close activity; discovery continues" onClick={onClose}>×</button></header>
      <div className="discovery-activity-scroll">
        <ResearchRunStatus kind="discovery" state={state} phase={text(study.phase)} message={text(job.status_message)} startedAt={text(study.created_at)} lastActivityAt={text(job.last_activity_at)} tests={Number(counts.tests || 0)} findings={Number(counts.supported_findings || 0)} cancelling={cancelling} connectionError={error} />
        <DataDiscoveryPhases phase={text(study.phase)} complete={complete} runState={state} />
        <p className="activity-progress-note">Progress follows completed analysis stages. Model requests have no reliable percentage estimate.</p>
        {Number(execution.queue_position) > 0 ? <p role="status">Queue position {Number(execution.queue_position)} · {Number(execution.active_workers || 0)} workers active</p> : null}
        <section><h3>Research objective</h3><p>{text(request.objective) || 'Discover scientifically interpretable relationships in the selected data.'}</p></section>
        <section><h3>Settings for this run</h3><dl className="activity-settings">
          <div><dt>Provider</dt><dd>{text(request.provider) || 'Local analysis'}</dd></div>
          <div><dt>Depth</dt><dd>{text(request.budget) || 'Balanced'}</dd></div>
          <div><dt>Reasoning model</dt><dd>{model('reasoning_model')}</dd></div>
          <div><dt>Vision model</dt><dd>{model('vision_model')}</dd></div>
          <div><dt>Knowledge sources</dt><dd>{text(request.knowledge_scope) || 'Combined'}</dd></div>
          <div><dt>Started</dt><dd>{text(study.created_at) ? new Date(text(study.created_at)).toLocaleString() : 'Waiting to start'}</dd></div>
        </dl><p className="activity-progress-note">Models show this run’s saved selection; Auto is resolved when the provider is contacted.</p></section>
        <section><h3>Selected data · {sourceIds.length} {sourceIds.length === 1 ? 'folder' : 'folders'}</h3>
          <p>{typeof coverage.total_bytes === 'number' ? `${Number(coverage.asset_count || 0).toLocaleString()} files inventoried · ${inventorySize(coverage.total_bytes)} · ${Number(coverage.view_count || 0).toLocaleString()} analyzable views` : 'File counts and sizes appear as each folder is inventoried.'}</p>
          <ul className="activity-sources">{sourceIds.map(id => { const source = sources.find(item => item.source_id === id), inventory = inventories.find(item => item.source_id === id); return <li key={id}><strong>{source?.display_name || id}</strong>{source?.display_location ? <span>{source.display_location}</span> : null}<small>{inventory ? `${Number(inventory.asset_count || 0).toLocaleString()} files · ${inventorySize(inventory.total_bytes)}` : complete ? 'No per-folder inventory receipt was saved for this run' : 'Inventory pending'}</small></li>; })}</ul>
        </section>
        <section><h3>Recent activity</h3>{children}</section>
      </div>
      <footer><span>{complete ? 'Completed evidence remains available.' : cancelling ? 'Stopping active work…' : 'You can close this window while discovery continues.'}</span><button onClick={onResults}>View results</button>{!complete ? <button className="activity-stop" disabled={cancelling} onClick={onStop}>{cancelling ? 'Stopping…' : 'Stop discovery'}</button> : null}</footer>
    </div>
  </FocusDialog>;
}
