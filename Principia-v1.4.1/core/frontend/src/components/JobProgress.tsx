import type { components } from "../api/schema";

type Job = components["schemas"]["JobRecord"];

export const terminalJobStates = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "Estimating";
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} sec`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes} min ${remainder.toString().padStart(2, "0")} sec`;
}

export function readableJobKind(kind: string): string {
  return {
    literature_search: "Literature search",
    local_source_index: "Folder indexing",
    literature_acquisition: "Paper acquisition",
    local_extraction: "Principle extraction",
    relation_index: "Relation analysis",
  }[kind] ?? kind.replaceAll("_", " ");
}

export function JobProgress({ job, compact = false }: { job: Job; compact?: boolean }) {
  const percent = Math.max(0, Math.min(100, Math.round(job.progress * 100)));
  const estimating = job.eta_seconds === null || job.eta_seconds === undefined;
  const terminal = terminalJobStates.has(job.state);
  return <div className={`durable-progress ${compact ? "compact" : ""}`} aria-live="polite">
    <div className="durable-progress-heading">
      <div><strong>{job.stage}</strong><small>{job.status_message || readableJobKind(job.kind)}</small></div>
      <span>{percent}%</span>
    </div>
    <div
      className="progress-track"
      role="progressbar"
      aria-label={`${readableJobKind(job.kind)} progress`}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={`${percent}% complete`}
    ><span style={{ width: `${percent}%` }} /></div>
    <div className="durable-progress-meta">
      <span>{job.total_units ? `${job.completed_units} of ${job.total_units} units` : "Preparing work units"}</span>
      <span>Elapsed {formatDuration(job.elapsed_seconds)}</span>
      {terminal ? <span>{job.state === "succeeded" ? "Finished" : "Stopped"}</span> : <span>Remaining {estimating ? "Estimating" : formatDuration(job.eta_seconds)}</span>}
      {job.retry_after_seconds ? <span className="rate-limit">Rate limit · retry in {formatDuration(job.retry_after_seconds)}</span> : null}
    </div>
  </div>;
}
