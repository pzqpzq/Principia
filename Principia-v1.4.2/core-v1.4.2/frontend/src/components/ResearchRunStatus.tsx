import { useEffect, useState } from "react";
import { formatDuration } from "./JobProgress";

export const finishedResearchStates = new Set([
  "succeeded", "partial", "failed", "cancelled", "interrupted", "data_insufficient",
]);

const phaseNames: Record<string, string> = {
  inventory: "Inspecting your data", understand: "Understanding the data structure",
  analyze: "Testing candidate relationships", challenge: "Checking candidate patterns",
  align: "Connecting relevant scientific knowledge", plan: "Planning candidate tests",
  execute: "Testing candidate relationships", synthesize: "Interpreting computed evidence",
  validate: "Checking the findings", report: "Preparing the results",
};

export function ResearchRunStatus({
  kind, state, phase = "", message = "", startedAt = "", lastActivityAt = "",
  tests = 0, findings = 0, connectionError = "", cancelling = false,
  onCancel, onActivity, onResults, onRetry,
}: {
  kind: "research" | "discovery"; state: string; phase?: string; message?: string;
  startedAt?: string; lastActivityAt?: string; tests?: number; findings?: number;
  connectionError?: string; cancelling?: boolean;
  onCancel?: () => void; onActivity?: () => void; onResults?: () => void; onRetry?: () => void;
}) {
  const [now, setNow] = useState(Date.now);
  const complete = finishedResearchStates.has(state);
  const paused = state === "paused";
  const working = !complete && !paused;
  useEffect(() => {
    setNow(Date.now());
    if (!working) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [working, startedAt]);
  const elapsed = Number.isFinite(Date.parse(startedAt))
    ? Math.max(0, (now - Date.parse(startedAt)) / 1000) : null;
  const silence = Number.isFinite(Date.parse(lastActivityAt))
    ? Math.max(0, (now - Date.parse(lastActivityAt)) / 1000) : 0;
  const stopped = ["failed", "cancelled", "interrupted", "data_insufficient"].includes(state);
  const title = connectionError ? "Progress connection interrupted"
    : cancelling ? "Stopping discovery…"
    : paused ? "Discovery paused"
    : complete ? ({ failed: "Discovery could not finish", cancelled: "Discovery cancelled",
        interrupted: "Discovery was interrupted", data_insufficient: "More usable data is needed",
        partial: "Discovery finished with partial results" }[state] || "Discovery complete")
    : kind === "research" ? "Finding relevant Principles"
    : phaseNames[phase] || (state === "queued" ? "Waiting to start discovery" : "Discovery in progress");
  return <section className={`research-run-status ${complete ? "finished" : "active"} ${stopped || connectionError ? "attention" : ""}`}
    aria-label={kind === "discovery" ? "Discovery progress" : "Search progress"}>
    <div className="research-run-status-copy">
      <div role="status" aria-live="polite">{working && !connectionError ? <span className="spinner" aria-hidden="true" /> : null}<strong>{title}</strong></div>
      <p>{connectionError || message || (kind === "research"
        ? "The map and results update automatically as the search is published."
        : "Your run is active. Findings will appear after their checks finish.")}</p>
      {working && silence >= 60 && !connectionError ? <p className="research-run-silence">No new worker update for {formatDuration(silence)}. You can keep waiting or stop discovery.</p> : null}
      <div className="research-run-status-metrics">
        {working && elapsed !== null ? <span>Elapsed {formatDuration(elapsed)}</span> : null}
        {kind === "discovery" ? <><span>{tests} {tests === 1 ? "test" : "tests"} completed</span><span>{findings} {findings === 1 ? "finding" : "findings"}</span></> : null}
        {working && !connectionError ? <span className="run-indeterminate" role="progressbar" aria-label="Work in progress" /> : null}
      </div>
    </div>
    <div className="research-run-status-actions">
      {connectionError && onRetry ? <button onClick={onRetry}>Reconnect</button> : null}
      {onActivity ? <button onClick={onActivity}>View activity</button> : null}
      {complete && onResults ? <button onClick={onResults}>View results</button> : null}
      {!complete && onCancel ? <button disabled={cancelling} onClick={onCancel}>{cancelling ? "Stopping…" : "Stop discovery"}</button> : null}
    </div>
  </section>;
}
