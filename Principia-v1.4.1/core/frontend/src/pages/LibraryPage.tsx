import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { ErrorState } from "../components/AsyncState";
import { JobProgress, terminalJobStates } from "../components/JobProgress";
import { PageHeader } from "../components/Shell";

type Collection = components["schemas"]["LibraryCollectionItem"];
type LocalSource = components["schemas"]["LocalSourceResponse"];
type WorkingDirectory = components["schemas"]["WorkingDirectoryResponse"];
type Job = components["schemas"]["JobRecord"];
type PrincipleGraph = components["schemas"]["PrincipleGraphViewResponse"];
type PotentialRelationsResponse = components["schemas"]["PotentialRelationsResponse"];
type VirtualGenerationResponse = components["schemas"]["VirtualPrincipleGenerationResponse"];
type VirtualPrincipleProposal = components["schemas"]["VirtualPrincipleProposal"];
type UnknownRecord = Record<string, unknown>;

const record = (value: unknown): UnknownRecord => value !== null && typeof value === "object" ? value as UnknownRecord : {};
const text = (value: unknown): string => typeof value === "string" ? value : "";
const terminalRunStates = new Set(["succeeded", "partial", "failed", "cancelled", "interrupted"]);
const HOME_GRAPH_LIMIT = 100;
const SharedPrincipleGraph = lazy(() => import("../components/PrincipleGraph").then((module) => ({ default: module.PrincipleGraph })));
const onlineFolderName = (value: string): string => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 56) || "public-literature";
const areaLabel = (value: string): string => ({
  "computer-science-ai": "Computer Science & AI",
  "economics-finance": "Economics & Finance",
  "neuroscience-cognitive-science": "Neuroscience & Cognitive Science",
  "biology-medicine": "Biology & Medicine",
  "chemistry-materials": "Chemistry & Materials",
  "engineering-robotics": "Engineering & Robotics",
  "earth-environmental-science": "Earth & Environmental Science",
  "social-behavioral-science": "Social & Behavioral Science",
  "law-policy": "Law & Policy",
  "interdisciplinary-science": "Interdisciplinary Science",
}[value] ?? value.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()));

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
  const [searchParams] = useSearchParams();
  const openedRun = useRef("");
  const [manualWorkingDirectory, setManualWorkingDirectory] = useState("");
  const [manualSourcePath, setManualSourcePath] = useState("");
  const [sourcePathOpen, setSourcePathOpen] = useState(false);
  const [researchGoal, setResearchGoal] = useState("");
  const [mapQuery, setMapQuery] = useState("");
  const [selectedAreas, setSelectedAreas] = useState<string[]>([]);
  const [selectedGraphPrinciple, setSelectedGraphPrinciple] = useState("");
  const [searchNotice, setSearchNotice] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
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

  useEffect(() => {
    const searchId = searchParams.get("online_search") || "";
    const jobId = searchParams.get("job") || "";
    if (!searchId) return;
    setOnlineSearchId(searchId);
    setOnlineSearchJobId(jobId);
    setOnlineOpen(true);
  }, [searchParams]);

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
  const homeAtlas = useQuery({
    queryKey: ["home-global-atlas", mapQuery, selectedAreas.join("|")],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/principles/graph", {
      params: { query: {
        scope: "global",
        q: mapQuery,
        area: selectedAreas.join(","),
        evidence_status: "checks_passed",
        sort: mapQuery ? "relevance" : "updated",
        limit: HOME_GRAPH_LIMIT,
        page: 1,
      } },
    })) as PrincipleGraph,
  });
  const homeAtlasFacets = useQuery({
    queryKey: ["home-global-atlas-facets"],
    queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/principles", { params: { query: { scope: "global", q: "", area: "", package_id: "", goal_id: "", source_id: "", goal_run_id: "", claim_type: "", evidence_status: "checks_passed", human_review: "", minimum_supporting_papers: 0, has_reliability: null, has_influence: null, known_contradictions: null, virtual_only: false, sort: "updated", limit: 1, cursor: null, page: 1 } } }))),
    staleTime: 60_000,
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
  const graphProvider = {
    provider: text(profile.provider_id) || text(profile.provider) || "siliconflow",
    label: text(profile.label) || "SiliconFlow",
    configured: profileConfigured,
    defaultModel: providerModel,
    models: profileModels,
  };
  const cloud = cloudStatus.data ?? {};
  const branches = Object.entries(record(goalRun.data?.branches));
  const recentRows: Collection[] = recentRuns.data?.items ?? [];
  const atlasCards = homeAtlas.data?.nodes ?? [];
  const atlasRelations = homeAtlas.data?.edges ?? [];
  const atlasTotal = homeAtlas.data?.total_count ?? 0;
  const atlasAreas = useMemo(() => {
    const values = record(homeAtlasFacets.data?.facets).areas;
    return (Array.isArray(values) ? values : []).map(record).map((item) => ({ value: text(item.value), count: Number(item.count ?? 0) })).filter((item) => item.value);
  }, [homeAtlasFacets.data]);

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
    const savedGoal = text(onlineSearch.data?.goal) || text(onlineSearch.data?.query);
    if (savedGoal) setOnlineQuestion((current) => current || savedGoal);
  }, [onlineSearch.data]);
  useEffect(() => {
    if (text(record(onlineAcquisitionJob.data).state) !== "succeeded") return;
    const sourceId = text(record(record(onlineAcquisitionJob.data).checkpoint).source_id);
    if (sourceId) setSelectedSources((current) => Array.from(new Set([...current, sourceId])));
    setResearchGoal(onlineQuestion);
    setOnlineOpen(false);
    queryClient.invalidateQueries({ queryKey: ["goal-run-sources"] });
  }, [record(onlineAcquisitionJob.data).state]);
  useEffect(() => setSelectedGraphPrinciple(""), [mapQuery, selectedAreas.join("|")]);

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
  const addFolderPath = useMutation({
    mutationFn: async () => {
      const source = record(dataOrThrow(await api.POST("/api/v1/local/sources", { body: { path: manualSourcePath.trim() } })));
      const sourceId = text(source.source_id);
      if (sourceId) await dataOrThrow(await api.POST("/api/v1/local/sources/{source_id}/indexes", { params: { path: { source_id: sourceId } } }));
      return source;
    },
    onSuccess: (value) => {
      const sourceId = text(value.source_id);
      if (sourceId) setSelectedSources((current) => Array.from(new Set([...current, sourceId])));
      setManualSourcePath("");
      setSourcePathOpen(false);
      queryClient.invalidateQueries({ queryKey: ["goal-run-sources"] });
    },
  });
  const disconnectFolder = useMutation({
    mutationFn: async (sourceId: string) => dataOrThrow(await api.DELETE("/api/v1/library/collections/{kind}/{collection_id}", { params: { path: { kind: "source", collection_id: sourceId } } })),
    onSuccess: (_, sourceId) => {
      setSelectedSources((current) => current.filter((item) => item !== sourceId));
      queryClient.invalidateQueries({ queryKey: ["goal-run-sources"] });
      queryClient.invalidateQueries({ queryKey: ["explorer-folders"] });
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
        goal: researchGoal.trim(), source_ids: selectedSources, include_global: true,
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
  const analyzePotentialRelations = async (principleIds: string[]): Promise<PotentialRelationsResponse> =>
    dataOrThrow(await api.POST("/api/v1/principles/potential-relations", {
      body: { principle_ids: principleIds },
    }));
  const generateVirtualPrinciples = async ({ principleIds, model: selectedModel, researchDirection }: { principleIds: string[]; model: string; researchDirection: string }): Promise<VirtualGenerationResponse> =>
    dataOrThrow(await api.POST("/api/v1/principles/virtual-principles/generate", {
      body: { principle_ids: principleIds, provider_profile_id: graphProvider.provider, model: selectedModel, egress_confirmed: true, requested_count: 3, research_direction: researchDirection },
    }));
  const saveVirtualPrinciple = async (proposal: VirtualPrincipleProposal, generation: VirtualGenerationResponse): Promise<{ candidate_id?: string }> => {
    const value = dataOrThrow(await api.POST("/api/v1/principles/virtual-principles/save", {
      body: { proposal, provider: generation.provider, model: generation.model, trace: generation.trace },
    })) as { candidate_id?: string };
    queryClient.invalidateQueries({ queryKey: ["home-global-atlas"] });
    queryClient.invalidateQueries({ queryKey: ["principle-cards"] });
    return value;
  };

  const toggleSource = (sourceId: string, checked: boolean) => {
    setSelectedSources((current) => checked ? Array.from(new Set([...current, sourceId])) : current.filter((id) => id !== sourceId));
  };
  const localReady = !selectedSources.length || (profileConfigured && confirmEgress);
  const canSearch = researchGoal.trim().length === 0 || researchGoal.trim().length >= 8;
  const runSearch = () => {
    const goal = researchGoal.trim();
    if (!goal) {
      setMapQuery("");
      setSelectedAreas([]);
      setSearchNotice("");
      return;
    }
    if (goal.length < 8) return;
    setMapQuery(goal);
    setSearchNotice("");
    if (!selectedSources.length) return;
    if (!localReady) {
      setSearchNotice("The Global map is updated. Connect the LLM and confirm local analysis to extract from the selected folders too.");
      return;
    }
    startGoalRun.mutate();
  };
  const cloudLabel = Boolean(cloud.available)
    ? `${String(cloud.work_count ?? 0)} papers · ${String(cloud.principle_count ?? 0)} Principles`
    : "Offline — Local search still works";
  const primaryError = workingDirectory.error ?? chooseWorkingDirectory.error ?? switchWorkingDirectory.error
    ?? addFolders.error ?? addFolderPath.error ?? disconnectFolder.error ?? saveCredential.error ?? startGoalRun.error ?? goalRun.error ?? cancelGoalRun.error
    ?? startOnlineSearch.error ?? onlineSearch.error ?? acquireOnline.error ?? onlineAcquisitionJob.error ?? homeAtlas.error;
  const onlineRows = (Array.isArray(onlineSearch.data?.results) ? onlineSearch.data.results : []).map(record);

  return <div className="page library-page concise-library home-map-page">
    <PageHeader
      eyebrow="Principia knowledge map"
      title="Explore what science knows"
      description="Describe a problem. Principia finds Principles that can help solve it, then lets you explore the surrounding map."
    />

    <section className="workspace-strip" aria-label="Current working directory">
      <div><span className="status-dot online" /><span>Working directory</span><strong>{workingDirectory.data?.display_name ?? "Opening…"}</strong></div>
      <button onClick={() => chooseWorkingDirectory.mutate()} disabled={!Boolean(workingDirectoryPicker.data?.available) || chooseWorkingDirectory.isPending}>{chooseWorkingDirectory.isPending ? "Choosing…" : "Change"}</button>
      <details><summary>Use a path</summary><form onSubmit={(event) => { event.preventDefault(); switchWorkingDirectory.mutate(); }}><input value={manualWorkingDirectory} onChange={(event) => setManualWorkingDirectory(event.target.value)} placeholder="/absolute/path/to/workspace" /><button disabled={!manualWorkingDirectory.trim()}>Open</button></form></details>
    </section>

    <main className="home-command-deck" aria-labelledby="home-search-title">
      <form className="home-semantic-search" onSubmit={(event) => { event.preventDefault(); runSearch(); }}>
        <div className="home-search-label"><span>Global-first semantic search</span><strong id="home-search-title">What do you want to understand or solve?</strong><small>{cloudLabel}</small></div>
        <div className="home-search-input"><input autoFocus value={researchGoal} onChange={(event) => setResearchGoal(event.target.value)} placeholder="For example: How can multi-agent systems improve mathematical theorem proving?" /><button className="primary" disabled={!canSearch || startGoalRun.isPending || Boolean(runId && !terminalRunStates.has(text(goalRun.data?.state)))}>{startGoalRun.isPending ? "Starting…" : !researchGoal.trim() && mapQuery ? "Show all" : selectedSources.length && localReady ? "Search + extract locally" : "Search"}<span>→</span></button></div>
        <div className="home-search-foot"><span>Matches mechanisms and solutions—not only exact words.</span>{mapQuery || selectedAreas.length ? <button type="button" onClick={() => { setMapQuery(""); setResearchGoal(""); setSelectedAreas([]); setSearchNotice(""); }}>Clear search and areas</button> : null}</div>
      </form>

      <details className="home-local-tools">
        <summary><span><strong>Local folders</strong><small>Optional · {selectedSources.length ? `${selectedSources.length} selected` : "search Global only"}</small></span><b>＋</b></summary>
        <div className="home-local-tools-body">
          <div className="source-actions"><button className="primary quiet" onClick={() => addFolders.mutate()} disabled={addFolders.isPending}>{addFolders.isPending ? "Choosing folders…" : "+ Add local folders"}</button><button onClick={() => setSourcePathOpen((current) => !current)}>Use a folder path</button><button onClick={() => { setOnlineQuestion(researchGoal); setOnlineOpen(true); }}>Find papers online</button></div>
          {sourcePathOpen ? <form className="source-path-entry" onSubmit={(event) => { event.preventDefault(); addFolderPath.mutate(); }}><label htmlFor="home-local-folder-path">Existing local folder path</label><div className="input-action"><input id="home-local-folder-path" value={manualSourcePath} onChange={(event) => setManualSourcePath(event.target.value)} placeholder="/absolute/path/to/papers" autoFocus /><button className="primary" disabled={!manualSourcePath.trim() || addFolderPath.isPending}>{addFolderPath.isPending ? "Connecting…" : "Connect folder"}</button><button type="button" onClick={() => { setSourcePathOpen(false); setManualSourcePath(""); }}>Cancel</button></div><small>The folder stays in place; only its searchable index belongs to this working directory.</small></form> : null}
          {sourceRows.length ? <div className="source-chip-list">{sourceRows.map((source) => <div key={source.source_id} className={selectedSources.includes(source.source_id) ? "source-chip selected" : "source-chip"}><label title={source.display_name}><input type="checkbox" checked={selectedSources.includes(source.source_id)} onChange={(event) => toggleSource(source.source_id, event.target.checked)} /><span><strong>{source.display_name}</strong><small>{source.status === "indexing" ? "Indexing papers…" : source.status === "index_failed" ? "Indexing needs attention" : `${source.document_count} paper${source.document_count === 1 ? "" : "s"}`}</small></span></label><button type="button" className="source-chip-remove" aria-label={`Remove ${source.display_name}`} title="Disconnect folder; files stay untouched" disabled={disconnectFolder.isPending} onClick={() => { if (window.confirm(`Remove “${source.display_name}” from this working directory? The folder and its files will not be deleted.`)) disconnectFolder.mutate(source.source_id); }}>×</button></div>)}</div> : <p className="empty-inline">No local folders connected. Global search is ready.</p>}

          {selectedSources.length > 0 && !profileConfigured ? <div className="provider-setup" role="group" aria-label="Connect LLM provider"><div><strong>Connect the LLM for local extraction</strong><small>The key stays private in this working directory.</small></div><input type="password" value={credential} onChange={(event) => setCredential(event.target.value)} placeholder="SiliconFlow API key" autoComplete="off" /><button onClick={() => saveCredential.mutate()} disabled={credential.length < 8 || saveCredential.isPending}>Save key</button></div> : null}
          {credentialMessage ? <p className="inline-success" role="status">{credentialMessage}</p> : null}
          {selectedSources.length > 0 && profileConfigured ? <label className="egress-confirm"><input type="checkbox" checked={confirmEgress} onChange={(event) => setConfirmEgress(event.target.checked)} /><span>Use {text(profile.label) || "the selected LLM"} to analyze bounded excerpts from these folders. Nothing is uploaded to Global Cloud.</span></label> : null}
          <details className="goal-options"><summary>Model and result limits</summary><div><label><span>Model</span>{profileModels.length ? <select value={providerModel} onChange={(event) => setProviderModel(event.target.value)}>{profileModels.map((value) => <option key={value}>{value}</option>)}</select> : <input value={providerModel} onChange={(event) => setProviderModel(event.target.value)} />}</label><label><span>Local results</span><input type="number" min={1} max={500} value={localLimit} onChange={(event) => setLocalLimit(Number(event.target.value))} /></label><label><span>Global results</span><input type="number" min={1} max={200} value={globalLimit} onChange={(event) => setGlobalLimit(Number(event.target.value))} /></label></div></details>
        </div>
      </details>

      {searchNotice ? <p className="home-search-notice" role="status">{searchNotice}</p> : null}
      {runId ? <section className="goal-progress compact" aria-live="polite">
        <header><div><span className="eyebrow">Global search + local extraction</span><h2>{text(goalRun.data?.goal) || researchGoal}</h2></div><span className={`pill ${["succeeded", "partial"].includes(text(goalRun.data?.state)) ? "success" : ""}`}>{text(goalRun.data?.state) || "starting"}</span></header>
        <div className="branch-progress-list">{branches.map(([name, value]) => { const branch = record(value); const state = text(branch.state); return <div key={name}><span className={`branch-state ${state}`} aria-hidden="true" /> <strong>{branchLabel(name)}</strong><small>{branchMessage(name, branch)}</small></div>; })}</div>
        {["succeeded", "partial"].includes(text(goalRun.data?.state)) ? <p className="inline-success">Results are ready. Opening Results…</p> : text(goalRun.data?.state) === "failed" ? <div><p>No branch completed. Your data was not changed.</p><button onClick={() => { setRunId(""); openedRun.current = ""; }}>Try again</button></div> : <button className="quiet" onClick={() => cancelGoalRun.mutate()} disabled={cancelGoalRun.isPending}>Cancel</button>}
      </section> : null}
    </main>

    <section className="home-atlas-section shared-home-graph">
      <header className="home-graph-toolbar">
        <div><span className="eyebrow">Global knowledge map</span><h2>{mapQuery ? `${atlasTotal} relevant Principles` : `${atlasTotal} Cloud Principles`}</h2><small>{atlasCards.length < atlasTotal ? `Showing the top ${atlasCards.length} as a responsive map; search or choose disciplines to focus it.` : "Every matching Principle is shown."}</small></div>
        <div className="home-discipline-filter" aria-label="Filter map by discipline">
          {atlasAreas.map((area) => <button type="button" key={area.value} className={selectedAreas.includes(area.value) ? "selected" : ""} onClick={() => setSelectedAreas((current) => current.includes(area.value) ? current.filter((value) => value !== area.value) : [...current, area.value])}><span>{areaLabel(area.value)}</span><small>{area.count}</small></button>)}
          {selectedAreas.length ? <button type="button" className="clear" onClick={() => setSelectedAreas([])}>Clear</button> : null}
        </div>
      </header>
      {homeAtlas.isLoading ? <div className="home-atlas-shell"><div className="home-atlas-loading" role="status"><span /><strong>Opening the interactive map…</strong><small>The search controls remain available</small></div></div> : atlasCards.length ? <Suspense fallback={<div className="home-atlas-shell"><div className="home-atlas-loading" role="status"><span /><strong>Opening graph tools…</strong></div></div>}><SharedPrincipleGraph
        cards={atlasCards}
        relations={atlasRelations}
        selectedId={selectedGraphPrinciple}
        onSelectPrinciple={setSelectedGraphPrinciple}
        onAnalyzePotentialRelations={analyzePotentialRelations}
        provider={graphProvider}
        onGenerateVirtualPrinciples={generateVirtualPrinciples}
        onSaveVirtualPrinciple={saveVirtualPrinciple}
        onOpenSavedVirtualPrinciple={(candidateId) => navigate(`/map?scope=local&selected=${encodeURIComponent(candidateId)}`)}
        onOpenSavedVirtualLibrary={() => navigate("/map?scope=local&virtual=true")}
      /></Suspense> : <div className="home-atlas-shell"><div className="home-atlas-empty"><strong>No relevant Principles found</strong><span>Try a broader scientific formulation or clear the selected disciplines.</span>{mapQuery || selectedAreas.length ? <button onClick={() => { setMapQuery(""); setResearchGoal(""); setSelectedAreas([]); }}>Show the full map</button> : null}</div></div>}
    </section>

    {onlineOpen ? <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOnlineOpen(false); }}><aside className="literature-drawer home-literature-drawer" role="dialog" aria-modal="true" aria-labelledby="home-literature-title"><header><div><span className="eyebrow">Stay on Home</span><h2 id="home-literature-title">Find papers online</h2><p>Search, choose, and save papers into a new goal-named folder under this working directory’s <code>local_data/</code>.</p></div><button aria-label="Close online paper search" onClick={() => setOnlineOpen(false)}>×</button></header><section><label><span>Research goal</span><textarea value={onlineQuestion} onChange={(event) => setOnlineQuestion(event.target.value)} placeholder="What papers do you need?" /></label><label><span>Target papers</span><input type="number" min={1} max={50} value={onlineTarget} onChange={(event) => setOnlineTarget(Number(event.target.value))} /></label><button className="primary full" disabled={onlineQuestion.trim().length < 8 || startOnlineSearch.isPending} onClick={() => startOnlineSearch.mutate()}>{startOnlineSearch.isPending ? "Starting…" : "Find papers"}</button>{onlineSearchJob.data ? <JobProgress job={onlineSearchJob.data} compact /> : null}</section>{Boolean(onlineSearch.data?.selection_finalized) ? <section><div className="drawer-section-heading"><div><span className="step-label">Choose papers</span><h3>{onlineSelected.length} selected</h3><p>Folder: <code>local_data/{onlineFolderName(onlineQuestion)}</code></p></div><button onClick={() => setOnlineSelected(onlineRows.map((paper) => text(paper.work_id) || text(paper.id)).filter(Boolean))}>Select all</button></div><div className="drawer-paper-list">{onlineRows.map((paper) => { const id = text(paper.work_id) || text(paper.id); const checked = onlineSelected.includes(id); return <label className={checked ? "selected" : ""} key={id}><input type="checkbox" checked={checked} onChange={() => setOnlineSelected((current) => checked ? current.filter((value) => value !== id) : [...current, id])} /><span><strong>{text(paper.title)}</strong><small>{String(paper.year ?? "Year unknown")} · {text(paper.venue) || text(paper.source)}</small></span></label>; })}</div><button className="primary full" disabled={!onlineSelected.length || acquireOnline.isPending || Boolean(onlineAcquisitionJobId)} onClick={() => acquireOnline.mutate()}>{acquireOnline.isPending ? "Starting download…" : `Save ${onlineSelected.length} papers`}</button>{onlineAcquisitionJob.data ? <><JobProgress job={onlineAcquisitionJob.data} compact />{text(record(onlineAcquisitionJob.data).state) === "succeeded" ? <div className="inline-success"><strong>Papers saved and selected.</strong> Close this panel, then run your research goal to extract from them automatically.</div> : null}</> : null}</section> : null}</aside></div> : null}

    {primaryError ? <ErrorState error={primaryError} retry={() => { workingDirectory.refetch(); localSources.refetch(); cloudStatus.refetch(); homeAtlas.refetch(); }} /> : null}

    {recentRows.length ? <details className="recent-goals"><summary>Previous research goals <span>{recentRows.length}</span></summary><div>{recentRows.slice(0, 8).map((collection) => <button key={collection.collection_id} onClick={() => navigate(`/map?scope=local&goal=${encodeURIComponent(collection.collection_id)}`)}><span><strong>{collection.title}</strong><small>{collection.principle_count} Principles · {collection.work_count} papers</small></span><span>Open →</span></button>)}</div></details> : null}
    <details className="legacy-package-note"><summary>Legacy offline packages</summary><p><strong>Shared Principle Package Library:</strong> downloaded candidate packages remain <strong>Human review pending</strong>. Paper files not included. Existing .pcp packages remain readable in v1.4.1.</p></details>
  </div>;
}
