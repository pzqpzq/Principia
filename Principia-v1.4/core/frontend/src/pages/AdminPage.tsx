import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, dataOrThrow } from "../api/client";
import type { components } from "../api/schema";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
import { PageHeader } from "../components/Shell";

type Capsule = components["schemas"]["PrincipleCapsule"];
type Candidate = components["schemas"]["CandidatePrinciple"];
type QueueItem = { candidate: Candidate; status: string; decision?: { capsule?: Capsule | null } | null };

function uiUlid(): string {
  const alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
  let timestamp = Date.now();
  let value = "";
  for (let index = 0; index < 10; index += 1) { value = alphabet[timestamp % 32] + value; timestamp = Math.floor(timestamp / 32); }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  for (let index = 0; index < 16; index += 1) value += alphabet[bytes[index] % 32];
  return value;
}

function reviewedCapsule(item: QueueItem): Capsule {
  const now = new Date().toISOString();
  return {
    principle_id: `prn:${item.candidate.area}:${uiUlid()}`, area: item.candidate.area, version: 1,
    title: item.candidate.title, claim: item.candidate.claim, kind: item.candidate.kind,
    maturity: "supported", scope: item.candidate.scope,
    quality: { grade: "B", validity: 0.8, reproducibility: 0.8, evidence_strength: 0.8, generality: 0.8, usefulness: 0.8, assessed_by: "local-admin", assessed_at: now },
    falsifier: "A public replication using the declared scope fails under the stated conditions.",
    source_references: [{ work_id: `fixture:${item.candidate.candidate_id}`, title: "Synthetic public review fixture", url: "", doi: "", role: "evidence", public: true }],
    relations: [], generation_trace: [{ event_id: `evt:${uiUlid()}`, operation: "promote", actor: "local-admin", provider: "", model: "", prompt_template: "", prompt_sha256: "", input_sha256: "0".repeat(64), output_sha256: "1".repeat(64), run_id: "admin-ui", latency_ms: 0, input_tokens: 0, output_tokens: 0, retries: 0, created_at: now }],
    tags: ["synthetic", "reviewed"], source_count: 1, relation_count: 0, trace_count: 1,
    status: "active", content_digest: "", created_at: now, updated_at: now
  };
}

export function AdminPage() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<QueueItem | null>(null);
  const [title, setTitle] = useState("Synthetic harvested candidate");
  const [claim, setClaim] = useState("A fixture claim requiring explicit human review.");
  const [area, setArea] = useState("demo-admin");
  const [changeset, setChangeset] = useState<Record<string, unknown> | null>(null);
  const [publishReceipt, setPublishReceipt] = useState<Record<string, unknown> | null>(null);
  const runtime = useQuery({ queryKey: ["admin-runtime"], queryFn: async () => dataOrThrow(await api.GET("/api/v1/admin/runtime", {})) });
  const queue = useQuery({ queryKey: ["admin-review"], queryFn: async () => dataOrThrow(await api.GET("/api/v1/admin/review", {})) });
  const harvest = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/admin/harvest", { body: { candidate: { candidate_id: `cand:ui-${Date.now()}`, area, title, claim, kind: "hypothesis", scope: { statement: "Synthetic public fixture", conditions: [], exclusions: [], populations: [] }, falsifier: "", source_references: [], relations: [], generation_trace: [], assessment_status: "unassessed", raw_legacy_payload: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-review"] })
  });
  const decide = useMutation({
    mutationFn: async (decision: "approve" | "edit" | "merge" | "reject") => dataOrThrow(await api.POST("/api/v1/admin/review/{candidate_id}/decision", { params: { path: { candidate_id: selected!.candidate.candidate_id } }, body: { decision, capsule: decision === "approve" ? reviewedCapsule(selected!) : null, note: decision === "edit" ? "Return for explicit quality and source review." : "Reviewed in local Admin runtime.", merge_target: decision === "merge" ? "prn:demo-admin:00000000000000000000000000" : "" } })),
    onSuccess: () => { setSelected(null); queryClient.invalidateQueries({ queryKey: ["admin-review"] }); }
  });
  const rows = (queue.data?.items ?? []) as QueueItem[];
  const approved = rows.filter((item) => item.status === "approve" && item.decision?.capsule).map((item) => item.decision!.capsule!) as Capsule[];
  const build = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/admin/changesets", { body: { area: approved[0].area, base_package_version: "0.0.0", proposed_package_version: "1.0.0", expected_content_digest: "0".repeat(64), goal: "Synthetic Admin dry-run acceptance", capsules: approved } })),
    onSuccess: (value) => { setChangeset(value as Record<string, unknown>); setPublishReceipt(null); }
  });
  const publish = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/admin/changesets/{changeset_id}/publish", { params: { path: { changeset_id: String(changeset?.changeset_id ?? "") } }, body: { mode: "dry_run", output: null, confirmation: "" } })),
    onSuccess: (value) => setPublishReceipt(value as Record<string, unknown>)
  });

  return <div className="page admin-page">
    <PageHeader eyebrow="Governance Workspace" title="Admin Console" description="Harvest public material, review every Candidate, and export compact publication changesets." actions={<span className="pill success">Admin runtime</span>} />
    {runtime.isError ? <ErrorState error={runtime.error} /> : null}
    <section className="harvest-bar"><label><span>Area</span><input value={area} onChange={(event) => setArea(event.target.value)} /></label><label><span>Candidate title</span><input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label className="grow"><span>Claim</span><input value={claim} onChange={(event) => setClaim(event.target.value)} /></label><button className="primary" onClick={() => harvest.mutate()}>Harvest fixture</button></section>
    {harvest.isError || decide.isError || build.isError || publish.isError ? <ErrorState error={harvest.error ?? decide.error ?? build.error ?? publish.error} /> : null}
    {queue.isLoading ? <LoadingState label="Reading review queue…" /> : null}
    <div className="admin-layout"><section className="review-table"><div className="table-heading"><h2>Review queue</h2><span>{rows.length} Candidates</span></div>{!queue.isLoading && rows.length === 0 ? <EmptyState title="No Candidates waiting"><p>Harvest adds Candidates here; publication never occurs automatically.</p></EmptyState> : rows.map((item) => <button key={item.candidate.candidate_id} className={selected?.candidate.candidate_id === item.candidate.candidate_id ? "selected" : ""} onClick={() => setSelected(item)}><span className={`status-dot ${item.status === "pending" ? "warning" : "online"}`} /><span><strong>{item.candidate.title}</strong><small>{item.candidate.area} · {item.status}</small></span><span>›</span></button>)}</section><aside className="review-panel">{selected ? <><span className="eyebrow">Candidate Review</span><h2>{selected.candidate.title}</h2><p className="claim">{selected.candidate.claim}</p><div className="review-warning">Approval creates a complete reviewed Capsule with explicit fixture source, quality, falsifier, and trace fields.</div><label><span>Reviewer note</span><textarea defaultValue="Complete the scientific assessment before a real release." /></label><div className="decision-actions"><button onClick={() => decide.mutate("reject")}>Reject</button><button onClick={() => decide.mutate("merge")}>Merge</button><button onClick={() => decide.mutate("edit")}>Edit</button><button className="primary" onClick={() => decide.mutate("approve")}>Approve Capsule</button></div></> : <EmptyState title="Select a Candidate"><p>The review inspector keeps human judgment at the center of publication.</p></EmptyState>}</aside></div>
    <section className="publication-footer"><div><strong>Publication is dry-run only</strong><p>{approved.length} approved Capsule{approved.length === 1 ? "" : "s"}. GitHub writes remain disabled.</p></div><button onClick={() => build.mutate()} disabled={!approved.length || build.isPending}>Build changeset</button>{changeset ? <button className="primary" onClick={() => publish.mutate()} disabled={publish.isPending}>Dry-run export</button> : <span>{String(runtime.data?.publication_default ?? "dry_run")}</span>}</section>
    {changeset ? <section className="changeset-preview"><span className="eyebrow">Publication Changeset</span><h2>{String(changeset.changeset_id)}</h2><p>{String((changeset.operations as unknown[] | undefined)?.length ?? 0)} immutable operation(s) · expected base digest pinned</p>{publishReceipt ? <div className="review-warning" role="status">Dry run complete. No external write was performed.</div> : null}</section> : null}
  </div>;
}
