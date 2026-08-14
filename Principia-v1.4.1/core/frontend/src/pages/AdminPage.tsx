import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, dataOrThrow } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
import { PageHeader } from "../components/Shell";

type Tab = "Dashboard" | "Discover" | "Extract" | "Review & Compare" | "Publish";
type UnknownRecord = Record<string, unknown>;
const tabs: Tab[] = ["Dashboard", "Discover", "Extract", "Review & Compare", "Publish"];
const record = (value: unknown): UnknownRecord => value && typeof value === "object" ? value as UnknownRecord : {};
const text = (value: unknown): string => typeof value === "string" ? value : "";
const modelName = (value: string): string => value.split("/").at(-1) || value;
const failureMessage = (paper: UnknownRecord): string => {
  const error = record(paper.error);
  if (text(error.message)) return text(error.message);
  if (paper.state === "acquisition_failed") return "Full text could not be acquired; abstracts are not used for Admin extraction.";
  if (paper.state === "provider_failed") return "The LLM request failed. Test the connection, then retry this paper.";
  if (paper.state === "validation_quarantined") return "The model completed, but this paper contained no supported reusable finding for the goal. Repeating the same paper and model will not help.";
  if (paper.state === "cleanup_failed") return "Temporary source cleanup failed; this paper cannot be marked successful.";
  return "";
};
const reviewableStagedItems = (value: unknown): UnknownRecord[] =>
  (Array.isArray(value) ? value : [])
    .map(record)
    .filter((item) => item.entity !== "principle_work");

export function AdminPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("Dashboard");
  const [goal, setGoal] = useState("");
  const [targetCount, setTargetCount] = useState(50);
  const [providerProfile, setProviderProfile] = useState("siliconflow");
  const [model, setModel] = useState("deepseek-ai/DeepSeek-V4-Flash");
  const [concurrency, setConcurrency] = useState(4);
  const [campaignId, setCampaignId] = useState("");
  const [selectedWorks, setSelectedWorks] = useState<string[]>([]);
  const [browserQuery, setBrowserQuery] = useState("");
  const [browserEntity, setBrowserEntity] = useState<"paper" | "principle" | "all">("all");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [venue, setVenue] = useState("");
  const [author, setAuthor] = useState("");
  const [institution, setInstitution] = useState("");
  const [publicationStatus, setPublicationStatus] = useState("");
  const [fullText, setFullText] = useState("");
  const [pageMin, setPageMin] = useState("");
  const [pageMax, setPageMax] = useState("");
  const [pdfMbMin, setPdfMbMin] = useState("");
  const [pdfMbMax, setPdfMbMax] = useState("");
  const [source, setSource] = useState("");
  const [cloudPresence, setCloudPresence] = useState("");
  const [syncId, setSyncId] = useState("");
  const [credential, setCredential] = useState("");
  const [credentialMessage, setCredentialMessage] = useState("");
  const [bulkReviewMessage, setBulkReviewMessage] = useState("");

  const dashboard = useQuery({ queryKey: ["admin-dashboard"], queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/admin/dashboard", {}))), refetchInterval: 60_000 });
  const providers = useQuery({ queryKey: ["providers"], queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/providers", {}))) });
  const campaigns = useQuery({ queryKey: ["admin-campaigns"], queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/admin/campaigns", {}))), refetchInterval: 1_000 });
  const campaignRows = (Array.isArray(campaigns.data?.items) ? campaigns.data.items : []) as UnknownRecord[];
  const campaign = campaignRows.find((item) => text(item.campaign_id) === campaignId);
  const papers = useQuery({
    queryKey: ["admin-papers", campaignId, text(campaign?.state), yearFrom, yearTo, venue, author, institution, publicationStatus, fullText, pageMin, pageMax, pdfMbMin, pdfMbMax, source, cloudPresence],
    enabled: Boolean(campaignId),
    queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/admin/campaigns/{campaign_id}/papers", { params: { path: { campaign_id: campaignId }, query: { limit: 200, offset: 0, selected: null, year_from: yearFrom ? Number(yearFrom) : null, year_to: yearTo ? Number(yearTo) : null, venue, author, institution, publication_status: publicationStatus, full_text_status: fullText, page_min: pageMin ? Number(pageMin) : null, page_max: pageMax ? Number(pageMax) : null, pdf_bytes_min: pdfMbMin ? Number(pdfMbMin) * 1024 * 1024 : null, pdf_bytes_max: pdfMbMax ? Number(pdfMbMax) * 1024 * 1024 : null, source, cloud_presence: cloudPresence } } }))),
    refetchInterval: ["discovering", "extracting"].includes(text(campaign?.state)) ? 750 : false,
  });
  const staging = useQuery({ queryKey: ["admin-staging", campaignId], enabled: Boolean(campaignId), queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/admin/campaigns/{campaign_id}/staging", { params: { path: { campaign_id: campaignId } } }))), refetchInterval: text(campaign?.state) === "extracting" ? 2_000 : false });
  const browser = useQuery({ queryKey: ["admin-cloud-browser", browserQuery, browserEntity], enabled: tab === "Dashboard", queryFn: async () => record(dataOrThrow(await api.POST("/api/v1/cloud/search", { body: { entity: browserEntity, query: browserQuery, year_from: null, year_to: null, venues: [], institutions: [], areas: [], full_text_status: "", page_min: null, page_max: null, pdf_bytes_min: null, pdf_bytes_max: null, cursor: "", limit: 100, paper_cohort: 100 } }))) });
  const latestSync = useQuery({ queryKey: ["admin-sync-latest", campaignId], enabled: Boolean(campaignId), queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/admin/campaigns/{campaign_id}/syncs/latest", { params: { path: { campaign_id: campaignId } } }))) });
  const sync = useQuery({ queryKey: ["admin-sync", syncId], enabled: Boolean(syncId), queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/admin/syncs/{sync_id}", { params: { path: { sync_id: syncId } } }))), refetchInterval: (query) => ["published", "failed", "cancelled", "needs_resolution"].includes(text(record(query.state.data).state)) ? false : 5_000 });

  const createCampaign = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/admin/campaigns", { body: { research_goal: goal, target_count: targetCount, provider_profile_id: providerProfile, model, concurrency } })),
    onSuccess: (value) => { setCampaignId(text(value.campaign_id)); setTab("Discover"); queryClient.invalidateQueries({ queryKey: ["admin-campaigns"] }); },
  });
  const rediscoverBetter = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/admin/campaigns", { body: { research_goal: text(campaign?.research_goal), target_count: Number(campaign?.target_count || 50), provider_profile_id: campaignProvider, model: campaignModel, concurrency: Number(campaign?.concurrency || 4) } })),
    onSuccess: (value) => { setCampaignId(text(value.campaign_id)); setSelectedWorks([]); setTab("Discover"); queryClient.invalidateQueries({ queryKey: ["admin-campaigns"] }); },
  });
  const saveSelection = useMutation({ mutationFn: async () => dataOrThrow(await api.PATCH("/api/v1/admin/campaigns/{campaign_id}/selection", { params: { path: { campaign_id: campaignId } }, body: { work_ids: selectedWorks } })), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-papers"] }) });
  const extract = useMutation({ mutationFn: async () => { await saveSelection.mutateAsync(); return dataOrThrow(await api.POST("/api/v1/admin/campaigns/{campaign_id}/extract", { params: { path: { campaign_id: campaignId } }, body: { retry: false, egress_confirmed: true } })); }, onSuccess: () => { setTab("Extract"); queryClient.invalidateQueries({ queryKey: ["admin-campaigns"] }); } });
  const retryRecoverableFailures = useMutation({
    mutationFn: async () => {
      const workIds = recoverablePaperIds;
      if (!workIds.length) throw new Error("There are no recoverable papers to retry.");
      await dataOrThrow(await api.PATCH("/api/v1/admin/campaigns/{campaign_id}/selection", { params: { path: { campaign_id: campaignId } }, body: { work_ids: workIds } }));
      return dataOrThrow(await api.POST("/api/v1/admin/campaigns/{campaign_id}/extract", { params: { path: { campaign_id: campaignId } }, body: { retry: true, egress_confirmed: true } }));
    },
    onSuccess: () => { setSelectedWorks([]); queryClient.invalidateQueries({ queryKey: ["admin-campaigns"] }); queryClient.invalidateQueries({ queryKey: ["admin-papers"] }); },
  });
  const pauseExtraction = useMutation({ mutationFn: async (jobId: string) => dataOrThrow(await api.POST("/api/v1/admin/extractions/{job_id}/pause", { params: { path: { job_id: jobId } } })), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-campaigns"] }) });
  const resumeExtraction = useMutation({ mutationFn: async (jobId: string) => dataOrThrow(await api.POST("/api/v1/admin/extractions/{job_id}/resume", { params: { path: { job_id: jobId } } })), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-campaigns"] }) });
  const cancelExtraction = useMutation({ mutationFn: async (jobId: string) => dataOrThrow(await api.POST("/api/v1/admin/extractions/{job_id}/cancel", { params: { path: { job_id: jobId } } })), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-campaigns"] }) });
  const decision = useMutation({ mutationFn: async ({ stageId, action, confirmed }: { stageId: string; action: "add" | "update" | "retire" | "skip"; confirmed: boolean }) => dataOrThrow(await api.PATCH("/api/v1/admin/staging/{stage_id}/decision", { params: { path: { stage_id: stageId } }, body: { decision: action, confirmed_ambiguous: confirmed } })), onSuccess: () => staging.refetch() });
  const bulkAdd = useMutation({
    mutationFn: async () => dataOrThrow(await api.PATCH("/api/v1/admin/staging/decisions/bulk", { body: { stage_ids: reviewableStagedItems(staging.data?.items).filter((item) => !item.decision).map((item) => text(item.stage_id)), decision: "add" } })),
    onSuccess: async (value) => {
      const result = record(value);
      const added = Array.isArray(result.updated) ? result.updated.length : 0;
      const excluded = Number(result.excluded_ambiguous ?? 0);
      setBulkReviewMessage(`${added} clear item${added === 1 ? "" : "s"} accepted${excluded ? ` · ${excluded} ambiguous item${excluded === 1 ? "" : "s"} safely excluded` : ""}.`);
      await staging.refetch();
      setTab("Publish");
    },
  });
  const createSync = useMutation({ mutationFn: async () => dataOrThrow(await api.POST("/api/v1/admin/campaigns/{campaign_id}/syncs", { params: { path: { campaign_id: campaignId } }, body: { confirmation: `SUBMIT ${campaignId}`, mode: "dry_run" } })), onSuccess: (value) => setSyncId(text(value.sync_id)) });
  const submitSync = useMutation({ mutationFn: async (id: string) => dataOrThrow(await api.POST("/api/v1/admin/syncs/{sync_id}/submit", { params: { path: { sync_id: id } }, body: { confirmation: `PUBLISH ${id}`, mode: "github_pr" } })), onSuccess: () => { sync.refetch(); latestSync.refetch(); } });
  const publishReviewed = useMutation({
    mutationFn: async () => {
      const created = record(await createSync.mutateAsync());
      const id = text(created.sync_id);
      if (!id) throw new Error("The reviewed publication draft was not created.");
      setSyncId(id);
      if (text(created.state) === "reviewed") return submitSync.mutateAsync(id);
      return created;
    },
    onSuccess: () => { dashboard.refetch(); latestSync.refetch(); },
  });
  const saveCredential = useMutation({
    mutationFn: async () => dataOrThrow(await api.PUT("/api/v1/provider-profiles/{provider_id}/credential", { params: { path: { provider_id: providerProfile } }, body: { api_key: credential } })),
    onSuccess: () => {
      setCredential("");
      setCredentialMessage("API key saved privately in this Admin working directory.");
      queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });
  const testCredential = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/provider-profiles/{provider_id}/test", { params: { path: { provider_id: providerProfile } } })),
    onSuccess: (value) => {
      const result = record(value);
      setCredentialMessage(Boolean(result.ok)
        ? `Connection ready at ${text(result.base_url)}.`
        : `Connection failed: ${text(result.category) || "provider unavailable"}. Extraction was not started.`);
      queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  useEffect(() => { if (!campaignId && campaignRows.length) setCampaignId(text(campaignRows[0].campaign_id)); }, [campaignId, campaignRows]);
  useEffect(() => { if (latestSync.isSuccess) setSyncId(text(latestSync.data?.sync_id)); }, [campaignId, latestSync.data?.sync_id, latestSync.isSuccess]);
  const paperRows = (Array.isArray(papers.data?.items) ? papers.data.items : []) as UnknownRecord[];
  const stagedRows = (Array.isArray(staging.data?.items) ? staging.data.items : []) as UnknownRecord[];
  const reviewableRows = reviewableStagedItems(stagedRows);
  const undecidedRows = reviewableRows.filter((item) => !item.decision);
  const undecidedClearRows = undecidedRows.filter((item) => item.match_kind !== "ambiguous");
  const acceptedRows = reviewableRows.filter((item) => ["add", "update", "retire"].includes(text(item.decision)));
  const ambiguousRows = reviewableRows.filter((item) => item.match_kind === "ambiguous");
  const excludedAmbiguousRows = ambiguousRows.filter((item) => !item.decision || item.decision === "skip");
  const syncState = text(sync.data?.state);
  const syncError = record(sync.data?.error);
  const publicationComplete = syncState === "published";
  const publicationInFlight = Boolean(syncId && !["reviewed", "failed", "cancelled", "needs_resolution", "published"].includes(syncState));
  const publicationReady = Boolean(campaignId && acceptedRows.length && !undecidedClearRows.length);
  const dashboardCloud = record(dashboard.data?.cloud);
  const campaignState = text(campaign?.state);
  const campaignDiscovery = record(campaign?.discovery);
  const provider = record((Array.isArray(providers.data?.profiles) ? providers.data.profiles : []).find((item) => text(record(item).provider_id) === providerProfile) ?? (Array.isArray(providers.data?.profiles) ? providers.data.profiles : [])[0]);
  const providerConfigured = Boolean(provider.configured);
  const campaignModel = text(campaign?.model) || model;
  const campaignProvider = text(campaign?.provider_profile_id) || providerProfile;
  const providerFailures = paperRows.filter((paper) => paper.state === "provider_failed").length;
  const acquisitionFailures = paperRows.filter((paper) => paper.state === "acquisition_failed").length;
  const validationFailures = paperRows.filter((paper) => paper.state === "validation_quarantined").length;
  const stagedPapers = paperRows.filter((paper) => paper.state === "staged").length;
  const discovering = campaignState === "discovering" || createCampaign.isPending;
  const extractablePaperIds = paperRows.filter((paper) => paper.availability_status === "available" && paper.goal_relevant !== false).map((paper) => text(paper.work_id)).filter(Boolean);
  const metadataOnlyPapers = paperRows.filter((paper) => paper.availability_status !== "available" && paper.goal_relevant !== false).length;
  const offGoalPapers = paperRows.filter((paper) => paper.goal_relevant === false).length;
  const recoverablePaperIds = paperRows.filter((paper) => {
    if (paper.availability_status !== "available" || paper.goal_relevant === false) return false;
    if (paper.state === "provider_failed") return Boolean(record(paper.error).retryable ?? true);
    return paper.state === "acquisition_failed" && Boolean(record(paper.error).retryable);
  }).map((paper) => text(paper.work_id)).filter(Boolean);
  const tabError = campaigns.error ?? providers.error ?? createCampaign.error ?? rediscoverBetter.error ?? saveCredential.error ?? testCredential.error ?? (tab === "Dashboard" ? dashboard.error : null)
    ?? (tab === "Discover" ? papers.error ?? saveSelection.error ?? extract.error : null)
    ?? (tab === "Extract" ? extract.error ?? retryRecoverableFailures.error ?? pauseExtraction.error ?? resumeExtraction.error ?? cancelExtraction.error : null)
    ?? (tab === "Review & Compare" ? staging.error ?? decision.error ?? bulkAdd.error : null)
    ?? (tab === "Publish" ? sync.error ?? createSync.error ?? submitSync.error : null);

  useEffect(() => {
    if (syncState !== "published") return;
    queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["admin-cloud-browser"] });
  }, [queryClient, syncState]);
  useEffect(() => { setBulkReviewMessage(""); }, [campaignId]);

  const ambiguousReviewPanel = ambiguousRows.length ? <section className="ambiguous-review-panel" aria-label="Ambiguous review items">
    <header>
      <div><span className="eyebrow">Needs attention · {ambiguousRows.length}</span><h2>Ambiguous paper matches</h2></div>
      <span className="pill">{excludedAmbiguousRows.length} excluded by default</span>
    </header>
    <p>These possible duplicates never disable publication. They are excluded unless you explicitly choose how each one should enter the Cloud.</p>
    <div className="ambiguous-review-list">{ambiguousRows.map((item) => {
      const proposed = record(item.proposed);
      const current = record(item.current);
      const label = text(proposed.title) || text(proposed.claim) || text(item.stage_id);
      const currentLabel = text(current.title) || text(current.claim) || "No named Cloud match";
      const itemDecision = text(item.decision);
      const status = itemDecision === "update" ? "Update matched Cloud record" : itemDecision === "add" ? "Keep as a separate record" : "Excluded from this publication";
      return <article key={text(item.stage_id)}>
        <div><span className="pill">{String(item.entity)}</span><strong>{label}</strong><small>Possible Cloud match: {currentLabel}</small>{text(item.match_reason) ? <small>Reason: {text(item.match_reason)}</small> : null}</div>
        <div className="ambiguous-actions" aria-label={`Decision for ${label}`}>
          <span>{status}</span>
          <button className={itemDecision === "update" ? "primary" : ""} disabled={decision.isPending} onClick={() => decision.mutate({ stageId: text(item.stage_id), action: "update", confirmed: true })}>Update existing</button>
          <button className={itemDecision === "add" ? "primary" : ""} disabled={decision.isPending} onClick={() => decision.mutate({ stageId: text(item.stage_id), action: "add", confirmed: true })}>Keep separate</button>
          <button className={!itemDecision || itemDecision === "skip" ? "primary" : ""} disabled={decision.isPending} onClick={() => decision.mutate({ stageId: text(item.stage_id), action: "skip", confirmed: false })}>Exclude</button>
        </div>
      </article>;
    })}</div>
  </section> : null;

  return <div className="page admin-page">
    <PageHeader eyebrow="Global Cloud" title="Admin" description="Find papers, extract Principles, review the changes, and publish." actions={<span className="pill success">Admin mode</span>} />
    <nav className="admin-tabs" aria-label="Admin workflow">{tabs.map((value) => <button className={tab === value ? "selected" : ""} key={value} onClick={() => setTab(value)}>{value}</button>)}</nav>
    {tabError ? <ErrorState error={tabError} retry={() => { campaigns.refetch(); if (tab === "Discover") papers.refetch(); }} /> : null}
    {tab === "Extract" && validationFailures ? <section className="review-warning" role="status"><strong>{validationFailures} paper{validationFailures === 1 ? "" : "s"} completed without a publishable finding.</strong><p>These are scientific zero-results, not connection failures. Principia will not charge you to repeat the same paper with the same model. Start a focused replacement search instead.</p><button onClick={() => rediscoverBetter.mutate()} disabled={rediscoverBetter.isPending}>{rediscoverBetter.isPending ? "Finding better papers…" : "Find better papers for this goal"}</button></section> : null}

    {tab === "Dashboard" ? <section className="admin-dashboard">
      <div className="library-totals">{[[dashboardCloud.work_count, "Cloud papers"], [dashboardCloud.principle_count, "current Principles"], [dashboardCloud.principle_revision_count, "Principle revisions"], [dashboardCloud.principle_work_count, "provenance links"], [dashboardCloud.relation_count, "relations"], [dashboard.data?.pending_syncs, "pending syncs"]].map(([value, label]) => <div key={String(label)}><strong>{String(value ?? 0)}</strong><span>{String(label)}</span></div>)}</div>
      <article className="cloud-status-card"><span className="eyebrow">Published snapshot</span><h2>{String(dashboardCloud.release_id || "No verified release")}</h2><dl><div><dt>Commit</dt><dd><code>{String(dashboardCloud.commit_sha || "—")}</code></dd></div><div><dt>Digest</dt><dd><code>{String(dashboardCloud.content_digest || "—")}</code></dd></div><div><dt>Snapshot size</dt><dd>{Math.round(Number(dashboardCloud.snapshot_bytes ?? 0) / 1024 / 1024)} MiB</dd></div><div><dt>Embedding contract</dt><dd>{String(dashboardCloud.embedding_contract ?? "—")}</dd></div></dl>{dashboardCloud.last_error ? <div className="review-warning">Last sync: {String(dashboardCloud.last_error)}</div> : null}</article>
      <section className="cloud-browser-inline"><div className="section-heading"><div><span className="eyebrow">Cloud browser</span><h2>Browse this published Cloud</h2><p>Search papers and Principles in the same place as release health and counts.</p></div></div><div className="harvest-bar"><label className="grow"><span>Search</span><input value={browserQuery} onChange={(event) => setBrowserQuery(event.target.value)} placeholder="Search any paper or Principle" /></label><label><span>Entity</span><select value={browserEntity} onChange={(event) => setBrowserEntity(event.target.value as typeof browserEntity)}><option value="all">All</option><option value="paper">Papers</option><option value="principle">Principles</option></select></label></div>{browser.isLoading ? <LoadingState label="Searching the pinned Cloud snapshot…" /> : <div className="admin-paper-table">{(Array.isArray(browser.data?.items) ? browser.data.items : []).map((item) => <article key={text(record(item).id)}><span className="pill">{String(record(item).entity)}</span><div><strong>{text(record(item).title)}</strong><small>{text(record(item).venue) || text(record(item).area)} · {text(record(item).match_path)}</small><p>{text(record(item).claim) || text(record(item).abstract).slice(0, 260)}</p></div></article>)}</div>}</section>
    </section> : null}

    {tab === "Discover" ? <section className="admin-discover">
      <form className="admin-discovery-composer" onSubmit={(event) => { event.preventDefault(); createCampaign.mutate(); }}>
        <label className="grow"><span>Research goal</span><input autoFocus value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="For example: coordination mechanisms in multi-agent systems" /></label>
        <label><span>How many papers?</span><input type="number" min={1} max={20000} value={targetCount} onChange={(event) => setTargetCount(Number(event.target.value))} /></label>
        <button className="primary" disabled={goal.trim().length < 8 || createCampaign.isPending}>{createCampaign.isPending ? "Starting…" : "Find papers"}</button>
        <div className="admin-llm-receipt"><span>Extraction LLM</span><strong>{text(provider.label) || providerProfile} · {modelName(model)}</strong><small>{concurrency} parallel paper workers</small></div>
        <details><summary>Extraction model</summary><div><label><span>Provider</span><input value={providerProfile} onChange={(event) => setProviderProfile(event.target.value)} /></label><label><span>Model</span><input value={model} onChange={(event) => setModel(event.target.value)} /></label><label><span>Workers</span><input type="number" min={4} max={8} value={concurrency} onChange={(event) => setConcurrency(Number(event.target.value))} /></label></div></details>
      </form>
      {campaignRows.length ? <div className="admin-campaign-picker"><label><span>Current search</span><select value={campaignId} onChange={(event) => { setCampaignId(event.target.value); setSelectedWorks([]); }}>{campaignRows.map((item) => <option key={text(item.campaign_id)} value={text(item.campaign_id)}>{text(item.research_goal)} · {text(item.state).replaceAll("_", " ")}</option>)}</select></label></div> : null}
      {campaignId ? <div className={`discovery-status ${discovering ? "running" : "ready"}`} role="status"><span className="branch-state" aria-hidden="true" /><div><strong>{discovering ? `${Number(campaignDiscovery.queries_completed ?? 0)} of ${Number(campaignDiscovery.query_count ?? 10)} focused searches · ${Number(campaignDiscovery.result_count ?? 0)} relevant papers found` : `${extractablePaperIds.length} on-topic full-text papers ready`}</strong><small>{discovering ? `${Number(campaignDiscovery.extractable_count ?? 0)} currently have open full text. Results appear after the focused search set finishes.` : `${metadataOnlyPapers} on-topic metadata-only · ${offGoalPapers} legacy off-topic result${offGoalPapers === 1 ? "" : "s"}. Only valid full-text papers can be selected.`}</small></div></div> : null}
      {!providerConfigured ? <div className="provider-setup admin-provider-setup" role="group" aria-label="Connect extraction LLM"><div><strong>Connect the extraction LLM</strong><small>The API key stays in this Admin working directory and is never stored in the Cloud dataset.</small></div><input type="password" value={credential} onChange={(event) => setCredential(event.target.value)} placeholder="SiliconFlow API key" autoComplete="off" /><button onClick={() => saveCredential.mutate()} disabled={credential.length < 8 || saveCredential.isPending}>{saveCredential.isPending ? "Saving…" : "Save key"}</button></div> : <div className="provider-setup admin-provider-setup" role="group" aria-label="Extraction LLM status"><div><strong>{text(provider.label) || campaignProvider} · {modelName(campaignModel)}</strong><small>The model is fixed for this campaign. Principia tests the provider before dispatching any papers.</small></div><button onClick={() => testCredential.mutate()} disabled={testCredential.isPending}>{testCredential.isPending ? "Testing…" : "Test connection"}</button></div>}
      {credentialMessage ? <p className="inline-success" role="status">{credentialMessage}</p> : null}
      <details className="admin-filter-drawer"><summary>Filter papers</summary><div className="admin-filters"><label><span>Year from</span><input value={yearFrom} onChange={(event) => setYearFrom(event.target.value)} /></label><label><span>Year to</span><input value={yearTo} onChange={(event) => setYearTo(event.target.value)} /></label><label><span>Venue</span><input value={venue} onChange={(event) => setVenue(event.target.value)} /></label><label><span>Author</span><input value={author} onChange={(event) => setAuthor(event.target.value)} /></label><label><span>Institution</span><input value={institution} onChange={(event) => setInstitution(event.target.value)} /></label><label><span>Publication status</span><input value={publicationStatus} onChange={(event) => setPublicationStatus(event.target.value)} placeholder="published, preprint…" /></label><label><span>Full text</span><select value={fullText} onChange={(event) => setFullText(event.target.value)}><option value="">Any</option><option>available</option><option>unavailable</option><option>unknown</option><option>probe_failed</option></select></label><label><span>Pages min</span><input type="number" min={1} value={pageMin} onChange={(event) => setPageMin(event.target.value)} /></label><label><span>Pages max</span><input type="number" min={1} value={pageMax} onChange={(event) => setPageMax(event.target.value)} /></label><label><span>PDF MiB min</span><input type="number" min={0} value={pdfMbMin} onChange={(event) => setPdfMbMin(event.target.value)} /></label><label><span>PDF MiB max</span><input type="number" min={0} value={pdfMbMax} onChange={(event) => setPdfMbMax(event.target.value)} /></label><label><span>Source</span><input value={source} onChange={(event) => setSource(event.target.value)} /></label><label><span>Cloud presence</span><select value={cloudPresence} onChange={(event) => setCloudPresence(event.target.value)}><option value="">Any</option><option value="new">New</option><option value="exact">Exact</option><option value="strong_id">Existing ID</option><option value="ambiguous">Ambiguous</option></select></label></div></details>
      {!discovering && campaignId && !papers.isLoading && !paperRows.length ? <EmptyState title="No papers match"><p>Try clearing the filters or start a new search.</p></EmptyState> : null}
      {!discovering && paperRows.length ? <><div className="paper-selection-bar"><button disabled={!extractablePaperIds.length} onClick={() => setSelectedWorks(Array.from(new Set([...selectedWorks, ...extractablePaperIds])))}>Select all on-topic full text ({extractablePaperIds.length})</button><button onClick={() => setSelectedWorks([])} disabled={!selectedWorks.length}>Clear</button><span>{selectedWorks.length} selected</span></div><div className="admin-paper-table">{paperRows.map((paper) => { const id = text(paper.work_id); const goalRelevant = paper.goal_relevant !== false; const extractable = paper.availability_status === "available" && goalRelevant; return <article className={selectedWorks.includes(id) ? "selected" : ""} key={id}><label className="inline-check"><input type="checkbox" disabled={!extractable} checked={selectedWorks.includes(id)} aria-label={extractable ? `Select ${text(paper.title)}` : `${text(paper.title)} cannot be extracted for this goal`} onChange={(event) => setSelectedWorks((current) => event.target.checked ? Array.from(new Set([...current, id])) : current.filter((value) => value !== id))} /><span /></label><div><strong>{text(paper.title)}</strong><small>{text(paper.venue) || "Venue unknown"} · {String(paper.year ?? "year unknown")} · {!goalRelevant ? "Off-topic legacy result — cannot select" : extractable ? "On-topic full text ready" : "On-topic metadata only — cannot extract"} · Cloud: {String(paper.cloud_presence)}</small>{text(paper.abstract) ? <p>{text(paper.abstract).slice(0, 280)}</p> : null}</div></article>; })}</div></> : null}
      {!discovering && campaignId ? <div className="sticky-admin-action"><span><strong>{selectedWorks.length}</strong> selected · {text(provider.label) || campaignProvider} / {modelName(campaignModel)} {selectedWorks.length > 0 && selectedWorks.length < 4 ? "· select at least four" : !providerConfigured ? "· connect the LLM above" : ""}</span><button className="primary" disabled={selectedWorks.length < 4 || !providerConfigured || extract.isPending} onClick={() => extract.mutate()}>{extract.isPending ? "Testing LLM and starting…" : `Extract with ${modelName(campaignModel)}`}</button></div> : null}
    </section> : null}

    {tab === "Extract" ? <section><div className="cloud-status-card"><span className="eyebrow">Live extraction</span><h2>{text(record(campaign?.extraction).state) || text(campaign?.state) || "No active campaign"}</h2><div className="admin-live-progress"><span style={{ width: `${Math.max(2, Math.round(Number(record(campaign?.extraction).progress ?? 0) * 100))}%` }} /></div><p><strong>{Math.round(Number(record(campaign?.extraction).progress ?? 0) * 100)}%</strong> · {String(record(campaign?.extraction).status_message || "waiting")}. Paper rows update automatically; no refresh is needed.</p><dl><div><dt>LLM</dt><dd><strong>{text(provider.label) || campaignProvider} · {campaignModel}</strong></dd></div><div><dt>Workers</dt><dd>{String(campaign?.concurrency || 4)} paper workers</dd></div><div><dt>Completed</dt><dd>{String(record(campaign?.extraction).completed_units ?? 0)} of {String(record(campaign?.extraction).total_units ?? 0)} papers</dd></div><div><dt>Elapsed / ETA</dt><dd>{String(record(campaign?.extraction).elapsed_seconds ?? 0)}s / {record(campaign?.extraction).eta_seconds == null ? "calculating" : `${String(record(campaign?.extraction).eta_seconds)}s`}</dd></div></dl><div className="goal-run-actions">{(() => { const extraction = record(campaign?.extraction); const jobId = text(extraction.job_id); const state = text(extraction.state); return <><button disabled={!jobId || !["queued", "running", "resuming"].includes(state)} onClick={() => pauseExtraction.mutate(jobId)}>Pause after active cleanup</button><button disabled={!jobId || !["paused", "interrupted", "pausing"].includes(state)} onClick={() => resumeExtraction.mutate(jobId)}>Resume</button><button disabled={!jobId || ["succeeded", "cancelled", "failed"].includes(state)} onClick={() => { if (window.confirm("Cancel queued papers? Active workers will finish mandatory cleanup.")) cancelExtraction.mutate(jobId); }}>Cancel</button><button disabled={!recoverablePaperIds.length || retryRecoverableFailures.isPending} onClick={() => { if (window.confirm(`Retry ${recoverablePaperIds.length} recoverable paper${recoverablePaperIds.length === 1 ? "" : "s"} with ${campaignModel}? This may create paid provider calls.`)) retryRecoverableFailures.mutate(); }}>{retryRecoverableFailures.isPending ? "Testing LLM and retrying…" : `Retry ${recoverablePaperIds.length} recoverable paper${recoverablePaperIds.length === 1 ? "" : "s"}`}</button></>; })()}</div></div>{(providerFailures || acquisitionFailures || validationFailures || stagedPapers || campaignState === "extracting") ? <div className="library-totals"><div><strong>{paperRows.filter((paper) => ["downloading", "parsing", "extracting", "challenging", "validating", "staging", "deleting_source"].includes(String(paper.state))).length}</strong><span>active now</span></div><div><strong>{stagedPapers}</strong><span>staged</span></div><div><strong>{providerFailures}</strong><span>LLM failures</span></div><div><strong>{acquisitionFailures}</strong><span>full-text failures</span></div><div><strong>{validationFailures}</strong><span>quality held back</span></div></div> : null}<div className="admin-paper-table">{paperRows.filter((paper) => Boolean(paper.selected)).map((paper) => <article key={text(paper.work_id)}><span className={`pill ${paper.state === "staged" ? "success" : ""}`}>{String(paper.state).replaceAll("_", " ")}</span><div><strong>{text(paper.title)}</strong><small>{["queued", "discovered"].includes(String(paper.state)) ? "Waiting for a worker" : String(paper.availability_status)} · temporary source deletion is mandatory</small>{failureMessage(paper) ? <p className="field-error">{failureMessage(paper)}</p> : null}</div></article>)}</div></section> : null}

    {tab === "Review & Compare" ? <section><div className="goal-run-actions"><span>{stagedRows.filter((item) => item.entity === "work").length} papers · {stagedRows.filter((item) => item.entity === "principle").length} Principles · provenance links are managed automatically</span><button onClick={() => bulkAdd.mutate()} disabled={!undecidedRows.length || bulkAdd.isPending}>{bulkAdd.isPending ? "Applying review…" : "Add all clear items"}</button></div>{ambiguousReviewPanel}{bulkReviewMessage ? <p className="inline-success" role="status">{bulkReviewMessage} Continue to Publish.</p> : null}{!stagedRows.length ? <EmptyState title="Nothing staged"><p>Completed papers appear here as readable paper groups while extraction continues.</p></EmptyState> : <div className="review-paper-groups">{stagedRows.filter((item) => item.entity === "work").map((work) => { const proposedWork = record(work.proposed); const workId = text(proposedWork.work_id); const principles = stagedRows.filter((item) => item.entity === "principle" && stagedRows.some((link) => link.entity === "principle_work" && text(record(link.proposed).work_id) === workId && text(record(link.proposed).principle_id) === text(record(item.proposed).principle_id))); const renderDecision = (item: UnknownRecord) => { const ambiguous = item.match_kind === "ambiguous"; return <div className="decision-actions">{(["add", "update", "retire", "skip"] as const).map((action) => <button className={item.decision === action ? "primary" : ""} key={action} onClick={() => decision.mutate({ stageId: text(item.stage_id), action, confirmed: ambiguous && action !== "skip" })}>{action}</button>)}</div>; }; return <article className="review-paper-group" key={text(work.stage_id)}><header><div><span className="eyebrow">Paper</span><h2>{text(proposedWork.title) || "Untitled paper"}</h2><small>{text(proposedWork.venue) || "Venue unknown"} · {String(proposedWork.year ?? "year unknown")} · {principles.length} proposed Principle{principles.length === 1 ? "" : "s"}</small></div><span className={`pill ${work.match_kind === "new" ? "success" : ""}`}>{String(work.match_kind)}</span></header><div className="review-work-decision">{renderDecision(work)}</div><div className="review-principle-list">{principles.map((item) => { const proposed = record(item.proposed); const current = record(item.current); return <section key={text(item.stage_id)}><header><div><span className="eyebrow">Principle</span><h3>{text(proposed.title) || text(proposed.claim).slice(0, 100)}</h3></div><span className={`pill ${item.match_kind === "new" ? "success" : ""}`}>{String(item.match_kind)}</span></header><div className="side-by-side"><div><small>Current Cloud</small><p>{text(current.claim) || "No matching Principle"}</p></div><div><small>Proposed</small><p>{text(proposed.claim)}</p></div></div>{renderDecision(item)}</section>; })}</div></article>; })}</div>}</section> : null}

    {tab === "Publish" ? <section className="cloud-status-card"><span className="eyebrow">One reviewed batch · automatic publication</span><h2>Publish reviewed additions</h2><p>One confirmation packages every accepted paper, Principle, and provenance link into one atomic batch. Principia validates it, updates GitHub, builds the verified release, and installs it locally—no PR or manual merge is required.</p>{ambiguousReviewPanel}{publicationComplete ? <p className="inline-success" role="status">This reviewed batch is published and active in Dashboard and regular search.</p> : publicationReady ? <p className="inline-success" role="status">{acceptedRows.length} accepted item{acceptedRows.length === 1 ? " is" : "s are"} ready to publish{excludedAmbiguousRows.length ? ` · ${excludedAmbiguousRows.length} ambiguous item${excludedAmbiguousRows.length === 1 ? " is" : "s are"} excluded` : ""}.</p> : <p className="review-warning" role="status">{acceptedRows.length ? `Review ${undecidedClearRows.length} remaining clear item${undecidedClearRows.length === 1 ? "" : "s"}.` : "Accept at least one clear paper or Principle before publishing."} Ambiguous items never disable publishing and are safely excluded by default.</p>}<div className="goal-run-actions"><button className="primary" onClick={() => { if (window.confirm("Publish this reviewed batch automatically? Ambiguous items not individually accepted are excluded. Local staging remains available until the verified Cloud release succeeds.")) publishReviewed.mutate(); }} disabled={!publicationReady || publicationComplete || publishReviewed.isPending || publicationInFlight}>{publishReviewed.isPending ? "Submitting one publication…" : publicationComplete ? "Reviewed batch published" : "Publish reviewed additions"}</button>{syncId && syncState === "reviewed" ? <button onClick={() => submitSync.mutate(syncId)} disabled={submitSync.isPending}>Resume publication</button> : null}</div>{syncId ? <div className={syncState === "published" ? "inline-success" : "review-warning"}><strong>{syncState.replaceAll("_", " ") || "Loading publication state…"}</strong><br />{syncState === "needs_resolution" ? <>Publication validation stopped safely; staging was preserved. {text(syncError.category).replaceAll("_", " ") || "Open the activity for details"}.</> : "Principia will update Dashboard and regular search automatically after the verified release is installed."}{text(sync.data?.pr_url) ? <> <a href={text(sync.data?.pr_url)} target="_blank" rel="noreferrer">Open publication activity</a></> : null}{text(sync.data?.release_id) ? <> · Release {text(sync.data?.release_id)}</> : null}</div> : null}</section> : null}

  </div>;
}
