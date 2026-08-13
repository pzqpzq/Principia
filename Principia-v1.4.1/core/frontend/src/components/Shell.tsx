import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { JobProgress, readableJobKind, terminalJobStates } from "./JobProgress";

type Job = components["schemas"]["JobRecord"];

const nav = [
  { path: "/library", icon: "⌂", label: "Home" },
  { path: "/map", icon: "▤", label: "Results" },
  { path: "/local", icon: "◫", label: "Data & settings" }
];

export function Shell() {
  const navigate = useNavigate();
  const [activityOpen, setActivityOpen] = useState(false);
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/runtime", {}))
  });
  const adminMode = Boolean(runtime.data?.admin_mode);
  const demoMode = Boolean(runtime.data?.demo_mode);
  const jobs = useQuery({
    queryKey: ["activity-jobs"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs", { params: { query: { kind: "", limit: 50 } } })),
    refetchInterval: 3_000,
  });
  const jobRows: Job[] = jobs.data?.items ?? [];
  const activeJobs = jobRows.filter((job) => !terminalJobStates.has(job.state));

  useEffect(() => {
    if (!activeJobs.length || typeof EventSource === "undefined") return;
    const streams = activeJobs.map((job) => {
      const stream = new EventSource(`/api/v1/jobs/${encodeURIComponent(job.job_id)}/stream`);
      const refresh = () => jobs.refetch();
      for (const eventType of ["queued", "progress", "succeeded", "completed", "failed", "cancelled", "interrupted"]) {
        stream.addEventListener(eventType, refresh);
      }
      return stream;
    });
    return () => streams.forEach((stream) => stream.close());
  }, [activeJobs.map((job) => job.job_id).join("|")]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">P</span>
          <div><strong>Principia</strong><small>Scientific Discovery</small></div>
        </div>
        {demoMode ? <span className="demo-badge">Demo Data</span> : null}
        <nav aria-label="Primary navigation">
          {[...(adminMode ? [{ path: "/admin", icon: "◈", label: "Admin" }] : []), ...nav].map((item) => (
            <NavLink key={item.path} to={item.path} className={({ isActive }) => isActive ? "active" : ""}>
              <span aria-hidden="true">{item.icon}</span>{item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className={`status-dot ${runtime.isError ? "danger" : "online"}`} />
          <div><strong>{runtime.isError ? "Disconnected" : "Local runtime"}</strong><small>v{String(runtime.data?.version ?? "1.4.1")}</small></div>
        </div>
      </aside>
      <button className="activity-trigger" onClick={() => setActivityOpen((value) => !value)} aria-expanded={activityOpen} aria-controls="activity-center">
        <span aria-hidden="true">◷</span><strong>Jobs</strong>{activeJobs.length ? <b>{activeJobs.length}</b> : null}
      </button>
      {activityOpen ? <aside className="activity-center" id="activity-center" aria-label="Activity Center">
        <header><div><span className="eyebrow">Persistent operations</span><h2>Activity Center</h2></div><button aria-label="Close Activity Center" onClick={() => setActivityOpen(false)}>×</button></header>
        {!jobRows.length ? <p className="activity-empty">No operations have run in this workspace yet.</p> : jobRows.map((job) => { const checkpoint = (job.checkpoint ?? {}) as { source_id?: string }; const localRunUrl = job.kind === "local_extraction" && checkpoint.source_id ? `/local?stage=results&source=${encodeURIComponent(checkpoint.source_id)}&job=${encodeURIComponent(job.job_id)}` : ""; return <article key={job.job_id}>
          <div className="activity-title"><strong>{readableJobKind(job.kind)}</strong><span className={`job-state ${job.state}`}>{job.state}</span></div>
          <JobProgress job={job} compact />
          {job.error ? <small className="activity-error">{String((job.error as { message?: string }).message ?? "The operation needs attention.")}</small> : null}
          {localRunUrl ? <button className="activity-open-run" onClick={() => { navigate(localRunUrl); setActivityOpen(false); }}>{terminalJobStates.has(job.state) ? "Review results" : "Open live extraction"}</button> : null}
        </article>; })}
      </aside> : null}
      <main className="workspace"><Outlet /></main>
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: React.ReactNode }) {
  return (
    <header className="page-header">
      <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>
      {actions ? <div className="header-actions">{actions}</div> : null}
    </header>
  );
}
