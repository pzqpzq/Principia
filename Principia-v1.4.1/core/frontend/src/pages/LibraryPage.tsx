import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { ErrorState } from "../components/AsyncState";
import { JobProgress, terminalJobStates } from "../components/JobProgress";
import { PageHeader } from "../components/Shell";

type Collection = components["schemas"]["LibraryCollectionItem"];
type LocalSource = components["schemas"]["LocalSourceResponse"];
type WorkingDirectory = components["schemas"]["WorkingDirectoryResponse"];
type Job = components["schemas"]["JobRecord"];
type UnknownRecord = Record<string, unknown>;

const record = (value: unknown): UnknownRecord => value !== null && typeof value === "object" ? value as UnknownRecord : {};
const text = (value: unknown): string => typeof value === "string" ? value : "";
const terminalRunStates = new Set(["succeeded", "partial", "failed", "cancelled", "interrupted"]);
const onlineFolderName = (value: string): string => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 56) || "public-literature";

function branchLabel(name: string): string {
  if (name === "global") return "Global Cloud";
  return "Local folder";
}

function branchMessage(name: string, branch: UnknownRecord): string {
  const state = text(branch.state) || "queued";
  if (state === "queued") return "Waiting";
  if (state === "running") return name === "global" ? "Finding papers, then linked Principles" : text(branch.stage) || "Reading papers and extracting Principles";
  if (state === "succeeded") return "Complete";
  if (state === "failed") return "Unavailable — other results are preserved";
  return state.replaceAll("_", " ");
}

export function LibraryPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const selectionInitialized = useRef(false);
  const openedRun = useRef("");
  const [manualWorkingDirectory, setManualWorkingDirectory] = useState("");
  const [researchGoal, setResearchGoal] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [includeGlobalCloud, setIncludeGlobalCloud] = useState(true);
  const [confirmEgress, setConfirmEgress] = useState(false);
  const [providerModel, setProviderModel] = useState("deepseek-ai/DeepSeek-V4-Flash");
  const [credential, setCredential] = useState("");
  const [credentialMessage, setCredentialMessage] = useState("");
  const [globalLimit, setGlobalLimit] = useState(50);
  const [localLimit, setLocalLimit] = useState(20);
  const [runId, setRunId] = useState("");
  const [onlineOpen, setOnlineOpen] = useState(false);
  const [onlineQuestion, setOnlineQuestion] = useState("");
  const [onlineTarget, setOnlineTarget] = useState(20);
  const [onlineSearchId, setOnlineSearchId] = useState("");
  const [onlineSearchJobId, setOnlineSearchJobId] = useState("");
  const [onlineSelected, setOnlineSelected] = useState<string[]>([]);
  const [onlineAcquisitionJobId, setOnlineAcquisitionJobId] = useState("");

  const workingDirectory = useQuery({
    queryKey: ["working-directory"],
    queryFn: async () => dataOrThrow(await api.POST("/api/v1/runtime/working-directory/disclosure", {})) as WorkingDirectory,
  });
  const workingDirectoryPicker = useQuery({
    queryKey: ["working-directory-picker"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/runtime/working-directory/picker", {})),
  });
  const localSources = useQuery({
    queryKey: ["goal-run-sources"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/sources", {})),
    refetchInterval: 1_000,
  });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/providers", {}))),
  });
  const cloudStatus = useQuery({
    queryKey: ["global-cloud-status"],
    queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/cloud/status", {}))),
    refetchInterval: 60_000,
  });
  const recentRuns = useQuery({
    queryKey: ["library-collections", "research_goal", false],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/library/collections", { params: { query: { kind: "research_goal", include_archived: false } } })),
  });
  const goalRun = useQuery({
    queryKey: ["research-goal-run", runId],
    enabled: Boolean(runId),
    queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/research-goal-runs/{run_id}", { params: { path: { run_id: runId } } }))),
    refetchInterval: (query) => terminalRunStates.has(text(record(query.state.data).state)) ? false : 750,
  });
  const onlineSearchJob = useQuery({
    queryKey: ["job", onlineSearchJobId], enabled: Boolean(onlineSearchJobId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: onlineSearchJobId } } })) as Job,
    refetchInterval: (query) => terminalJobStates.has(text(record(query.state.data).state)) ? false : 750,
  });
  const onlineSearch = useQuery({
    queryKey: ["home-literature-search", onlineSearchId], enabled: Boolean(onlineSearchId),
    queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/local/literature-searches/{search_id}", { params: { path: { search_id: onlineSearchId } } }))),
    refetchInterval: (query) => Boolean(record(query.state.data).selection_finalized) ? false : 750,
  });
  const onlineAcquisitionJob = useQuery({
    queryKey: ["job", onlineAcquisitionJobId], enabled: Boolean(onlineAcquisitionJobId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: onlineAcquisitionJobId } } })) as Job,
    refetchInterval: (query) => terminalJobStates.has(text(record(query.state.data).state)) ? false : 750,
  });

  const sourceRows: LocalSource[] = localSources.data?.sources ?? [];
  const profile = record((Array.isArray(providers.data?.profiles) ? providers.data.profiles : [])[0]);
  const profileConfigured = Boolean(profile.configured);
  const profileModels = Array.isArray(profile.models) ? profile.models.map(String) : [];
  const cloud = cloudStatus.data ?? {};
  const branches = Object.entries(record(goalRun.data?.branches));
  const recentRows: Collection[] = recentRuns.data?.items ?? [];

  useEffect(() => {
    if (selectionInitialized.current || localSources.isLoading) return;
    selectionInitialized.current = true;
    setSelectedSources(sourceRows.filter((source) => source.status !== "removed").map((source) => source.source_id));
  }, [localSources.isLoading, sourceRows.length]);

  useEffect(() => {
    const state = text(goalRun.data?.state);
    if (!runId || !["succeeded", "partial"].includes(state) || openedRun.current === runId) return;
    openedRun.current = runId;
    const timer = window.setTimeout(() => navigate(`/map?scope=combined&goal_run=${encodeURIComponent(runId)}`), 650);
    return () => window.clearTimeout(timer);
  }, [runId, goalRun.data?.state, navigate]);
  useEffect(() => {
    if (!Boolean(onlineSearch.data?.selection_finalized)) return;
    setOnlineSelected((current) => current.length ? current : (Array.isArray(onlineSearch.data?.selected_work_ids) ? onlineSearch.data.selected_work_ids.map(String) : []));
  }, [onlineSearch.data?.selection_finalized]);
  useEffect(() => {
    if (text(record(onlineAcquisitionJob.data).state) !== "succeeded") return;
    const sourceId = text(record(record(onlineAcquisitionJob.data).checkpoint).source_id);
    if (sourceId) setSelectedSources((current) => Array.from(new Set([...current, sourceId])));
    setResearchGoal(onlineQuestion);
    setOnlineOpen(false);
    queryClient.invalidateQueries({ queryKey: ["goal-run-sources"] });
  }, [record(onlineAcquisitionJob.data).state]);

  const completeWorkingDirectorySwitch = () => {
    queryClient.clear();
    window.location.assign("/library");
  };
  const chooseWorkingDirectory = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/runtime/working-directory/choose", {})),
    onSuccess: completeWorkingDirectorySwitch,
  });
  const switchWorkingDirectory = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/runtime/working-directory/switch", { body: { path: manualWorkingDirectory } })),
    onSuccess: completeWorkingDirectorySwitch,
  });
  const addFolders = useMutation({
    mutationFn: async () => record(dataOrThrow(await api.POST("/api/v1/local/folder-picker/multiple", {}))),
    onSuccess: (value) => {
      const added = (Array.isArray(value.sources) ? value.sources : []).map(record).map((source) => text(source.source_id)).filter(Boolean);
      setSelectedSources((current) => Array.from(new Set([...current, ...added])));
      queryClient.invalidateQueries({ queryKey: ["goal-run-sources"] });
    },
  });
  const saveCredential = useMutation({
    mutationFn: async () => dataOrThrow(await api.PUT("/api/v1/provider-profiles/{provider_id}/credential", { params: { path: { provider_id: "siliconflow" } }, body: { api_key: credential } })),
    onSuccess: () => {
      setCredential("");
      setCredentialMessage("API key saved privately in this working directory.");
      queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });
  const startGoalRun = useMutation({
    mutationFn: async () => record(dataOrThrow(await api.POST("/api/v1/research-goal-runs", {
      params: { query: { egress_confirmed: selectedSources.length > 0 && confirmEgress } },
      body: {
        goal: researchGoal.trim(), source_ids: selectedSources, include_global: includeGlobalCloud,
        include_online: false, provider_profile_id: "siliconflow", model: providerModel,
        local_limit: localLimit, global_limit: globalLimit,
      },
    }))),
    onSuccess: (value) => setRunId(text(value.run_id)),
  });
  const startOnlineSearch = useMutation({
    mutationFn: async () => record(dataOrThrow(await api.POST("/api/v1/local/literature-searches", { body: { query: onlineQuestion.trim(), goal: "", area: "", target_count: onlineTarget, semantic_ranking: true, source_id: "" } }))),
    onSuccess: (job) => {
      setOnlineSearchJobId(text(job.job_id));
      setOnlineSearchId(text(record(job.checkpoint).search_id));
      setOnlineSelected([]);
    },
  });
  const acquireOnline = useMutation({
    mutationFn: async () => {
      await dataOrThrow(await api.PATCH("/api/v1/local/literature-searches/{search_id}/selection", { params: { path: { search_id: onlineSearchId } }, body: { work_ids: onlineSelected } }));
      return record(dataOrThrow(await api.POST("/api/v1/local/literature-searches/{search_id}/acquisitions", { params: { path: { search_id: onlineSearchId } }, body: { source_id: null, folder_name: onlineFolderName(onlineQuestion), work_ids: onlineSelected } })));
    },
    onSuccess: (job) => setOnlineAcquisitionJobId(text(job.job_id)),
  });
  const cancelGoalRun = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/research-goal-runs/{run_id}/cancel", { params: { path: { run_id: runId } } })),
    onSuccess: () => goalRun.refetch(),
  });

  const toggleSource = (sourceId: string, checked: boolean) => {
    setSelectedSources((current) => checked ? Array.from(new Set([...current, sourceId])) : current.filter((id) => id !== sourceId));
  };
  const localReady = !selectedSources.length || (profileConfigured && confirmEgress);
  const canRun = researchGoal.trim().length >= 8 && (includeGlobalCloud || selectedSources.length > 0) && localReady;
  const cloudLabel = Boolean(cloud.available)
    ? `${String(cloud.work_count ?? 0)} papers · ${String(cloud.principle_count ?? 0)} Principles`
    : "Offline — Local search still works";
  const primaryError = workingDirectory.error ?? chooseWorkingDirectory.error ?? switchWorkingDirectory.error
    ?? addFolders.error ?? saveCredential.error ?? startGoalRun.error ?? goalRun.error ?? cancelGoalRun.error
    ?? startOnlineSearch.error ?? onlineSearch.error ?? acquireOnline.error ?? onlineAcquisitionJob.error;
  const onlineRows = (Array.isArray(onlineSearch.data?.results) ? onlineSearch.data.results : []).map(record);

  return <div className="page library-page concise-library">
    <PageHeader
      eyebrow="One goal, all your knowledge"
      title="What are you researching?"
      description="Principia searches the Global Cloud and your chosen folders together, then opens one clear result set."
    />

    <section className="workspace-strip" aria-label="Current working directory">
      <div><span className="status-dot online" /><span>Working directory</span><strong>{workingDirectory.data?.display_name ?? "Opening…"}</strong></div>
      <button onClick={() => chooseWorkingDirectory.mutate()} disabled={!Boolean(workingDirectoryPicker.data?.available) || chooseWorkingDirectory.isPending}>{chooseWorkingDirectory.isPending ? "Choose in system dialog…" : "Change"}</button>
      <details><summary>Use a path</summary><form onSubmit={(event) => { event.preventDefault(); switchWorkingDirectory.mutate(); }}><input value={manualWorkingDirectory} onChange={(event) => setManualWorkingDirectory(event.target.value)} placeholder="/absolute/path/to/workspace" /><button disabled={!manualWorkingDirectory.trim()}>Open</button></form></details>
    </section>

    <main className="goal-composer" aria-labelledby="goal-composer-title">
      <section className="goal-step sources-step">
        <header><span>1</span><div><h2 id="goal-composer-title">Choose your knowledge</h2><p>Local folders are optional. Add several at once or search only the Cloud.</p></div></header>
        <div className="source-actions"><button className="primary quiet" onClick={() => addFolders.mutate()} disabled={addFolders.isPending}>{addFolders.isPending ? "Choose folders in the system dialog…" : "+ Add local folders"}</button><button onClick={() => { setOnlineQuestion(researchGoal); setOnlineOpen(true); }}>Find papers online</button></div>
        {sourceRows.length ? <div className="source-chip-list">{sourceRows.map((source) => <label key={source.source_id} className={selectedSources.includes(source.source_id) ? "source-chip selected" : "source-chip"}><input type="checkbox" checked={selectedSources.includes(source.source_id)} onChange={(event) => toggleSource(source.source_id, event.target.checked)} /><span><strong>{source.display_name}</strong><small>{source.status === "indexing" ? "Indexing papers…" : source.status === "index_failed" ? "Indexing needs attention" : `${source.document_count} paper${source.document_count === 1 ? "" : "s"}`}</small></span></label>)}</div> : <p className="empty-inline">No local folders connected. That is fine — Global Cloud is on.</p>}
      </section>

      <section className="goal-step question-step">
        <header><span>2</span><div><h2>Enter one research goal</h2><p>Describe the mechanism, design rule, or boundary you want to understand.</p></div></header>
        <textarea autoFocus value={researchGoal} onChange={(event) => setResearchGoal(event.target.value)} placeholder="For example: Which coordination mechanisms make multi-agent systems robust to communication failures?" />
        <label className="cloud-toggle"><input type="checkbox" checked={includeGlobalCloud} onChange={(event) => setIncludeGlobalCloud(event.target.checked)} /><span><strong>Search Global Cloud</strong><small>{cloudLabel}</small></span></label>

        {selectedSources.length > 0 && !profileConfigured ? <div className="provider-setup" role="group" aria-label="Connect LLM provider"><div><strong>Connect the LLM for local extraction</strong><small>The key stays in this working directory and never enters the Cloud.</small></div><input type="password" value={credential} onChange={(event) => setCredential(event.target.value)} placeholder="SiliconFlow API key" autoComplete="off" /><button onClick={() => saveCredential.mutate()} disabled={credential.length < 8 || saveCredential.isPending}>Save key</button></div> : null}
        {credentialMessage ? <p className="inline-success" role="status">{credentialMessage}</p> : null}
        {selectedSources.length > 0 && profileConfigured ? <label className="egress-confirm"><input type="checkbox" checked={confirmEgress} onChange={(event) => setConfirmEgress(event.target.checked)} /><span>Use {text(profile.label) || "the selected LLM"} to analyze bounded excerpts from my selected folders. Nothing is uploaded to Global Cloud.</span></label> : null}

        <details className="goal-options"><summary>Model and result limits</summary><div><label><span>Model</span>{profileModels.length ? <select value={providerModel} onChange={(event) => setProviderModel(event.target.value)}>{profileModels.map((value) => <option key={value}>{value}</option>)}</select> : <input value={providerModel} onChange={(event) => setProviderModel(event.target.value)} />}</label><label><span>Local results</span><input type="number" min={1} max={500} value={localLimit} onChange={(event) => setLocalLimit(Number(event.target.value))} /></label><label><span>Global results</span><input type="number" min={1} max={200} value={globalLimit} onChange={(event) => setGlobalLimit(Number(event.target.value))} /></label></div></details>
        <button className="run-goal-button" onClick={() => startGoalRun.mutate()} disabled={!canRun || startGoalRun.isPending || Boolean(runId && !terminalRunStates.has(text(goalRun.data?.state)))}>{startGoalRun.isPending ? "Starting…" : selectedSources.length ? "Search Cloud + extract from my folders" : "Search Global Cloud"}</button>
        {!localReady && selectedSources.length > 0 ? <small className="run-helper">Connect the LLM and confirm local analysis to continue.</small> : null}
      </section>

      {runId ? <section className="goal-progress" aria-live="polite">
        <header><div><span className="eyebrow">Running your goal</span><h2>{text(goalRun.data?.goal) || researchGoal}</h2></div><span className={`pill ${["succeeded", "partial"].includes(text(goalRun.data?.state)) ? "success" : ""}`}>{text(goalRun.data?.state) || "starting"}</span></header>
        <div className="branch-progress-list">{branches.map(([name, value]) => { const branch = record(value); const state = text(branch.state); return <div key={name}><span className={`branch-state ${state}`} aria-hidden="true" /> <strong>{branchLabel(name)}</strong><small>{branchMessage(name, branch)}</small></div>; })}</div>
        {["succeeded", "partial"].includes(text(goalRun.data?.state)) ? <p className="inline-success">Results are ready. Opening Explorer…</p> : text(goalRun.data?.state) === "failed" ? <div><p>Neither branch completed. Your folders and Cloud data were not changed.</p><button onClick={() => { setRunId(""); openedRun.current = ""; }}>Try again</button></div> : <button className="quiet" onClick={() => cancelGoalRun.mutate()} disabled={cancelGoalRun.isPending}>Cancel</button>}
      </section> : null}
    </main>

    {onlineOpen ? <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOnlineOpen(false); }}><aside className="literature-drawer home-literature-drawer" role="dialog" aria-modal="true" aria-labelledby="home-literature-title"><header><div><span className="eyebrow">Stay on Home</span><h2 id="home-literature-title">Find papers online</h2><p>Search, choose, and save papers into a new goal-named folder under this working directory’s <code>local_data/</code>.</p></div><button aria-label="Close online paper search" onClick={() => setOnlineOpen(false)}>×</button></header><section><label><span>Research goal</span><textarea value={onlineQuestion} onChange={(event) => setOnlineQuestion(event.target.value)} placeholder="What papers do you need?" /></label><label><span>Target papers</span><input type="number" min={1} max={50} value={onlineTarget} onChange={(event) => setOnlineTarget(Number(event.target.value))} /></label><button className="primary full" disabled={onlineQuestion.trim().length < 8 || startOnlineSearch.isPending} onClick={() => startOnlineSearch.mutate()}>{startOnlineSearch.isPending ? "Starting…" : "Find papers"}</button>{onlineSearchJob.data ? <JobProgress job={onlineSearchJob.data} compact /> : null}</section>{Boolean(onlineSearch.data?.selection_finalized) ? <section><div className="drawer-section-heading"><div><span className="step-label">Choose papers</span><h3>{onlineSelected.length} selected</h3><p>Folder: <code>local_data/{onlineFolderName(onlineQuestion)}</code></p></div><button onClick={() => setOnlineSelected(onlineRows.map((paper) => text(paper.work_id) || text(paper.id)).filter(Boolean))}>Select all</button></div><div className="drawer-paper-list">{onlineRows.map((paper) => { const id = text(paper.work_id) || text(paper.id); const checked = onlineSelected.includes(id); return <label className={checked ? "selected" : ""} key={id}><input type="checkbox" checked={checked} onChange={() => setOnlineSelected((current) => checked ? current.filter((value) => value !== id) : [...current, id])} /><span><strong>{text(paper.title)}</strong><small>{String(paper.year ?? "Year unknown")} · {text(paper.venue) || text(paper.source)}</small></span></label>; })}</div><button className="primary full" disabled={!onlineSelected.length || acquireOnline.isPending || Boolean(onlineAcquisitionJobId)} onClick={() => acquireOnline.mutate()}>{acquireOnline.isPending ? "Starting download…" : `Save ${onlineSelected.length} papers`}</button>{onlineAcquisitionJob.data ? <><JobProgress job={onlineAcquisitionJob.data} compact />{text(record(onlineAcquisitionJob.data).state) === "succeeded" ? <div className="inline-success"><strong>Papers saved and selected.</strong> Close this panel, then run your research goal to extract from them automatically.</div> : null}</> : null}</section> : null}</aside></div> : null}

    {primaryError ? <ErrorState error={primaryError} retry={() => { workingDirectory.refetch(); localSources.refetch(); cloudStatus.refetch(); }} /> : null}

    {recentRows.length ? <details className="recent-goals"><summary>Previous research goals <span>{recentRows.length}</span></summary><div>{recentRows.slice(0, 8).map((collection) => <button key={collection.collection_id} onClick={() => navigate(`/map?scope=local&goal=${encodeURIComponent(collection.collection_id)}`)}><span><strong>{collection.title}</strong><small>{collection.principle_count} Principles · {collection.work_count} papers</small></span><span>Open →</span></button>)}</div></details> : null}
    <details className="legacy-package-note"><summary>Legacy offline packages</summary><p><strong>Shared Principle Package Library:</strong> downloaded candidate packages remain <strong>Human review pending</strong>. Paper files not included. Existing .pcp packages remain readable in v1.4.1.</p></details>
  </div>;
}
