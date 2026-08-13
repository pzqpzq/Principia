import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
import { PageHeader } from "../components/Shell";

type CollectionKind = "research_goal" | "area" | "source";
type Collection = components["schemas"]["LibraryCollectionItem"];
type WorkingDirectory = components["schemas"]["WorkingDirectoryResponse"];
type AreaObject = { [key: string]: unknown };

function objectValue(value: unknown): AreaObject {
  return value !== null && typeof value === "object" ? value as AreaObject : {};
}

function textValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

const GROUP_LABELS: Record<CollectionKind, string> = {
  research_goal: "Research Goals",
  area: "Areas",
  source: "Private Folders",
};

export function LibraryPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [kind, setKind] = useState<CollectionKind>("research_goal");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [editingTitle, setEditingTitle] = useState("");
  const [catalogPath, setCatalogPath] = useState("");
  const [globalFilter, setGlobalFilter] = useState<"all" | "installed" | "available">("all");
  const [manualWorkingDirectory, setManualWorkingDirectory] = useState("");
  const [showManualWorkingDirectory, setShowManualWorkingDirectory] = useState(false);
  const [researchGoal, setResearchGoal] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [includeGlobalCloud, setIncludeGlobalCloud] = useState(true);
  const [includeOnline, setIncludeOnline] = useState(false);
  const [goalAdvanced, setGoalAdvanced] = useState(false);
  const [providerModel, setProviderModel] = useState("deepseek-ai/DeepSeek-V4-Flash");
  const [globalLimit, setGlobalLimit] = useState(50);
  const [localLimit, setLocalLimit] = useState(20);

  const workingDirectory = useQuery({
    queryKey: ["working-directory"],
    queryFn: async () => dataOrThrow(await api.POST("/api/v1/runtime/working-directory/disclosure", {})) as WorkingDirectory,
  });
  const workingDirectoryPicker = useQuery({
    queryKey: ["working-directory-picker"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/runtime/working-directory/picker", {})),
  });
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

  const summary = useQuery({
    queryKey: ["library-summary"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/library/summary", {})),
  });
  const collections = useQuery({
    queryKey: ["library-collections", kind, includeArchived],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/library/collections", {
      params: { query: { kind, include_archived: includeArchived } },
    })),
  });
  const areas = useQuery({
    queryKey: ["areas"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/areas", {})),
  });
  const localSources = useQuery({
    queryKey: ["goal-run-sources"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/sources", {})),
  });
  const cloudStatus = useQuery({
    queryKey: ["global-cloud-status"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/cloud/status", {})),
    refetchInterval: 60_000,
  });
  const startGoalRun = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/research-goal-runs", {
      params: { query: { egress_confirmed: selectedSources.length > 0 } },
      body: {
        goal: researchGoal,
        source_ids: selectedSources,
        include_global: includeGlobalCloud,
        include_online: includeOnline,
        provider_profile_id: "siliconflow",
        model: providerModel,
        local_limit: localLimit,
        global_limit: globalLimit,
      },
    })),
    onSuccess: (data) => navigate(`/map?scope=combined&goal_run=${encodeURIComponent(String(data.run_id))}`),
  });
  const refresh = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/areas/catalog/refresh", {
      body: { path: catalogPath },
    })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["areas"] }),
  });
  const packageAction = useMutation({
    mutationFn: async ({ area, action, version, pinned }: {
      area: string;
      action: "install" | "update" | "verify" | "pin" | "rollback";
      version?: string;
      pinned?: boolean;
    }) => {
      if (action === "install") return dataOrThrow(await api.POST("/api/v1/areas/{area}/install", { params: { path: { area } }, body: { version: version ?? null } }));
      if (action === "update") return dataOrThrow(await api.POST("/api/v1/areas/{area}/update", { params: { path: { area } }, body: { version: version ?? null } }));
      if (action === "verify") return dataOrThrow(await api.POST("/api/v1/areas/{area}/verify", { params: { path: { area } }, body: { version: version ?? null } }));
      if (action === "pin") return dataOrThrow(await api.POST("/api/v1/areas/{area}/pin", { params: { path: { area } }, body: { version: version ?? "" , pinned: pinned ?? true } }));
      return dataOrThrow(await api.POST("/api/v1/areas/{area}/rollback", { params: { path: { area } } }));
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["areas"] }),
  });
  const reveal = useMutation({
    mutationFn: async (sourceId: string) => dataOrThrow(await api.POST("/api/v1/local/sources/{source_id}/reveal", {
      params: { path: { source_id: sourceId } },
    })),
  });
  const editCollection = useMutation({
    mutationFn: async ({ collection, title }: { collection: Collection; title: string }) => dataOrThrow(await api.PATCH("/api/v1/library/collections/{kind}/{collection_id}", {
      params: { path: { kind: collection.kind, collection_id: collection.collection_id } }, body: { title },
    })),
    onSuccess: () => { setEditingId(""); setEditingTitle(""); queryClient.invalidateQueries({ queryKey: ["library-collections"] }); queryClient.invalidateQueries({ queryKey: ["library-summary"] }); },
  });
  const archiveCollection = useMutation({
    mutationFn: async (collection: Collection) => dataOrThrow(await api.DELETE("/api/v1/library/collections/{kind}/{collection_id}", {
      params: { path: { kind: collection.kind, collection_id: collection.collection_id } },
    })),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["library-collections"] }); queryClient.invalidateQueries({ queryKey: ["library-summary"] }); },
  });
  const restoreCollection = useMutation({
    mutationFn: async (collection: Collection) => dataOrThrow(await api.POST("/api/v1/library/collections/{kind}/{collection_id}/restore", {
      params: { path: { kind: collection.kind as "research_goal" | "source", collection_id: collection.collection_id } },
    })),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["library-collections"] }); queryClient.invalidateQueries({ queryKey: ["library-summary"] }); },
  });

  const collectionRows: Collection[] = collections.data?.items ?? [];
  const areaPayload = objectValue(areas.data);
  const cloudPayload = objectValue(cloudStatus.data);
  const globalRows = (Array.isArray(areaPayload.areas) ? areaPayload.areas : [])
    .map(objectValue)
    .filter((item) => globalFilter === "all" || (globalFilter === "installed" ? Boolean(item.installed) : !item.installed));
  const mapUrl = (collection: Collection) => {
    if (collection.kind === "research_goal") return `/map?scope=local&goal=${encodeURIComponent(collection.collection_id)}`;
    if (collection.kind === "area") return `/map?scope=local&area=${encodeURIComponent(collection.area)}`;
    return `/map?scope=local&source=${encodeURIComponent(collection.source_id)}`;
  };

  return <div className="page library-page">
    <PageHeader
      eyebrow="Your scientific knowledge workspace"
      title="Principles Library"
      description="Browse the same private Principle corpus by Research Goal, Area, or Folder. These are overlapping views—not duplicate data."
      actions={<button className="primary" onClick={() => navigate("/local?stage=folder")}>+ Add private folder</button>}
    />

    <section className="working-directory-card" aria-label="Active working directory">
      <div className="working-directory-copy"><span className="eyebrow">Active working directory</span><div className="working-directory-title"><h2>{workingDirectory.data?.display_name ?? "Opening workspace…"}</h2>{workingDirectory.data ? <span className={workingDirectory.data.empty ? "pill" : "pill success"}>{workingDirectory.data.empty ? "Empty" : "Contains local knowledge"}</span> : null}</div><code>{workingDirectory.data?.working_directory ?? "Resolving exact path…"}</code><p>This folder isolates its <strong>workspace</strong>, <strong>local_data</strong>, credentials, jobs, and private Principles. Downloaded Principle packages live in one shared application library and remain available when you switch working directories.</p></div>
      <div className="working-directory-actions"><button className="primary" onClick={() => { if (window.confirm("Switch the entire Principia workspace? The current directory remains unchanged on disk.")) chooseWorkingDirectory.mutate(); }} disabled={!Boolean(workingDirectoryPicker.data?.available) || chooseWorkingDirectory.isPending}>{chooseWorkingDirectory.isPending ? "Choose a folder in the system dialog…" : "Choose working directory…"}</button><button onClick={() => setShowManualWorkingDirectory((value) => !value)} aria-expanded={showManualWorkingDirectory}>Enter absolute path</button></div>
      {showManualWorkingDirectory ? <form className="working-directory-manual" onSubmit={(event) => { event.preventDefault(); if (window.confirm("Switch the entire Principia workspace? The current directory remains unchanged on disk.")) switchWorkingDirectory.mutate(); }}><label><span>Existing folder on this computer</span><input value={manualWorkingDirectory} onChange={(event) => setManualWorkingDirectory(event.target.value)} placeholder="/absolute/path/to/working-directory" /></label><button className="primary" disabled={!manualWorkingDirectory.trim() || switchWorkingDirectory.isPending}>{switchWorkingDirectory.isPending ? "Switching workspace…" : "Open this working directory"}</button></form> : null}
      {workingDirectory.data ? <div className="working-directory-boundaries"><span><strong>Raw Local data</strong><code>{workingDirectory.data.local_data}</code></span><span><strong>Durable private knowledge</strong><code>{workingDirectory.data.workspace}</code></span>{workingDirectory.data.package_library ? <span><strong>Shared Principle packages</strong><code>{workingDirectory.data.package_library}</code></span> : null}</div> : null}
    </section>
    {workingDirectory.isError || chooseWorkingDirectory.isError || switchWorkingDirectory.isError ? <ErrorState error={workingDirectory.error ?? chooseWorkingDirectory.error ?? switchWorkingDirectory.error} retry={() => workingDirectory.refetch()} /> : null}

    <section className="research-goal-panel" aria-labelledby="new-research-goal-title">
      <div><span className="eyebrow">Global + private knowledge</span><h2 id="new-research-goal-title">New research goal</h2><p>Search the pinned Global Cloud immediately while selected private folders run independently. No private content is uploaded to the Cloud.</p></div>
      <label><span>Research goal</span><textarea value={researchGoal} onChange={(event) => setResearchGoal(event.target.value)} placeholder="Which scientific mechanisms or boundary conditions should I investigate?" /></label>
      <fieldset><legend>Private folders (optional, multiple)</legend><div className="goal-source-grid">{(localSources.data?.sources ?? []).map((source) => <label className="inline-check" key={source.source_id}><input type="checkbox" checked={selectedSources.includes(source.source_id)} onChange={(event) => setSelectedSources((current) => event.target.checked ? [...current, source.source_id] : current.filter((value) => value !== source.source_id))} /><span>{source.display_name} · {source.document_count} papers</span></label>)}</div></fieldset>
      <div className="goal-run-options"><label className="inline-check"><input type="checkbox" checked={includeGlobalCloud} onChange={(event) => setIncludeGlobalCloud(event.target.checked)} /><span>Include Global Cloud ({String(cloudPayload.principle_count ?? 0)} Principles · {String(cloudPayload.work_count ?? 0)} papers)</span></label><label className="inline-check"><input type="checkbox" checked={includeOnline} onChange={(event) => setIncludeOnline(event.target.checked)} /><span>Search online literature (paper selection required before download)</span></label></div>
      <details open={goalAdvanced} onToggle={(event) => setGoalAdvanced(event.currentTarget.open)}><summary>Advanced settings</summary><div className="goal-advanced"><label><span>Provider model</span><input value={providerModel} onChange={(event) => setProviderModel(event.target.value)} /></label><label><span>Local limit</span><input type="number" min={1} max={500} value={localLimit} onChange={(event) => setLocalLimit(Number(event.target.value))} /></label><label><span>Global limit</span><input type="number" min={1} max={200} value={globalLimit} onChange={(event) => setGlobalLimit(Number(event.target.value))} /></label></div></details>
      <div className="goal-run-actions"><span className={`pill ${cloudPayload.available ? "success" : ""}`}>{cloudPayload.available ? `Cloud ${String(cloudPayload.release_id ?? "verified")}` : "Cloud offline · Local still available"}</span><button className="primary" onClick={() => startGoalRun.mutate()} disabled={researchGoal.trim().length < 8 || (!includeGlobalCloud && !includeOnline && !selectedSources.length) || startGoalRun.isPending}>{startGoalRun.isPending ? "Starting branches…" : "Run research goal"}</button></div>
      {startGoalRun.isError ? <ErrorState error={startGoalRun.error} /> : null}
    </section>

    <section className="library-totals" aria-label="Private workspace totals">
      {[
        [summary.data?.principle_count, "Principles ready to review"],
        [summary.data?.document_count, "indexed papers"],
        [summary.data?.research_goal_count, "research goals"],
        [summary.data?.area_count, "scientific areas"],
        [summary.data?.source_count, "private folders"],
        [summary.data?.quarantined_count, "held-back drafts"],
      ].map(([value, label]) => <div key={String(label)}><strong>{summary.isLoading ? "—" : String(value ?? 0)}</strong><span>{label}</span></div>)}
    </section>
    {summary.data?.needs_revalidation_count ? <div className="quality-notice" role="status"><strong>{summary.data.needs_revalidation_count} older drafts are hidden.</strong><span>They remain in the audit record and will return after updated evidence checks.</span></div> : null}
    {summary.isError ? <ErrorState error={summary.error} retry={() => summary.refetch()} /> : null}

    <section className="private-collections" aria-labelledby="private-collection-title">
      <div className="collection-heading">
        <div><span className="eyebrow">Private workspace</span><h2 id="private-collection-title">Collections</h2><p>{collections.data?.explanation ?? "Choose how you want to enter the same Principle corpus."}</p></div>
        <div className="segmented" aria-label="Group private Principles">
          {(Object.keys(GROUP_LABELS) as CollectionKind[]).map((value) => <button key={value} className={kind === value ? "selected" : ""} aria-pressed={kind === value} onClick={() => setKind(value)}>{GROUP_LABELS[value]}</button>)}
        </div>
        {kind !== "area" ? <label className="inline-check collection-archive-control"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} /><span>Show archived</span></label> : <span className="collection-archive-control" aria-hidden="true" />}
      </div>
      {collections.isLoading ? <LoadingState label={`Loading ${GROUP_LABELS[kind]}…`} /> : null}
      {collections.isError ? <ErrorState error={collections.error} retry={() => collections.refetch()} /> : null}
      {editCollection.isError || archiveCollection.isError || restoreCollection.isError ? <ErrorState error={editCollection.error ?? archiveCollection.error ?? restoreCollection.error} /> : null}
      {!collections.isLoading && !collections.isError && !collectionRows.length ? <EmptyState title={`No ${GROUP_LABELS[kind]} yet`}><p>Choose or create a private folder in Local Discovery. Literature Search can help populate one when you do not already have papers.</p><button className="primary" onClick={() => navigate("/local?stage=folder")}>Open Local Discovery</button></EmptyState> : null}
      <div className="collection-grid">{collectionRows.map((collection) => <article className="collection-card" key={collection.collection_id}>
        <div className="card-top"><span className={`collection-icon ${collection.kind}`}>{collection.kind === "research_goal" ? "G" : collection.kind === "area" ? "A" : "F"}</span><span className={`pill ${collection.status === "ready" || collection.status === "active" ? "success" : ""}`}>{collection.status}</span></div>
        <span className="collection-kind">{GROUP_LABELS[collection.kind].replace(/s$/, "")}</span>
        {editingId === collection.collection_id ? <form className="collection-edit" onSubmit={(event) => { event.preventDefault(); editCollection.mutate({ collection, title: editingTitle }); }}><label><span>{collection.kind === "area" ? "Area label" : "Name"}</span><input autoFocus value={editingTitle} onChange={(event) => setEditingTitle(event.target.value)} /></label><div><button className="primary" disabled={!editingTitle.trim() || editCollection.isPending}>Save</button><button type="button" onClick={() => setEditingId("")}>Cancel</button></div></form> : <h3>{collection.kind === "area" ? collection.title.replaceAll("-", " ") : collection.title}</h3>}
        {collection.source_name ? <p className="collection-location">{collection.source_name}{collection.display_location ? ` · ${collection.display_location}` : ""}</p> : <p className="collection-location">{collection.area.replaceAll("-", " ") || "Cross-area"}</p>}
        <div className="collection-metrics"><div><strong>{collection.principle_count}</strong><span>Principles</span></div><div><strong>{collection.work_count}</strong><span>Papers</span></div><div><strong>{collection.evidence_count}</strong><span>Evidence</span></div><div><strong>{collection.quarantined_count}</strong><span>Held back</span></div></div>
        {collection.needs_revalidation_count ? <p className="revalidation-count">{collection.needs_revalidation_count} older drafts await updated checks</p> : null}
        <div className="card-actions"><button className="primary" onClick={() => navigate(mapUrl(collection))}>Open Explorer</button>{collection.kind === "source" && collection.status !== "removed" ? <button onClick={() => navigate(`/local?stage=papers&source=${encodeURIComponent(collection.source_id)}`)}>Select papers</button> : null}{collection.kind === "source" && collection.status !== "removed" ? <button onClick={() => reveal.mutate(collection.source_id)}>Open Folder</button> : null}<button onClick={() => { setEditingId(collection.collection_id); setEditingTitle(collection.kind === "area" ? collection.title.replaceAll("-", " ") : collection.title); }}>Rename</button>{collection.status === "archived" || collection.status === "removed" ? <button onClick={() => restoreCollection.mutate(collection)} disabled={collection.kind === "area"}>Restore</button> : <button onClick={() => { const action = collection.kind === "source" ? "disconnect this folder from Principia (files remain on disk)" : collection.kind === "area" ? "remove this Area label and move its Principles to Not categorized" : "archive this Research Goal"; if (window.confirm(`Are you sure you want to ${action}?`)) archiveCollection.mutate(collection); }}>{collection.kind === "source" ? "Disconnect" : collection.kind === "area" ? "Remove label" : "Archive"}</button>}</div>
      </article>)}</div>
    </section>

    <details className="global-packages" open={globalRows.length > 0}>
      <summary><span><strong>Shared Principle Package Library</strong><small>Downloaded once, available in every working directory · paper files excluded</small></span><span>{globalRows.length}</span></summary>
      <div className="global-package-content">
        <section className="toolbar-card" aria-label="Global catalog configuration">
          <label><span>Principle catalog file</span><input value={catalogPath} onChange={(event) => setCatalogPath(event.target.value)} placeholder="Choose catalog.json" /></label>
          <button className="primary" onClick={() => refresh.mutate()} disabled={!catalogPath || refresh.isPending}>Refresh catalog</button>
          <div className="segmented" aria-label="Global package filter">{(["all", "installed", "available"] as const).map((value) => <button key={value} className={globalFilter === value ? "selected" : ""} onClick={() => setGlobalFilter(value)}>{value}</button>)}</div>
        </section>
        {areas.isLoading ? <LoadingState label="Reading shared Principle packages…" /> : null}
        {areas.isError ? <ErrorState error={areas.error} retry={() => areas.refetch()} /> : null}
        {refresh.isError || packageAction.isError || reveal.isError ? <ErrorState error={refresh.error ?? packageAction.error ?? reveal.error} /> : null}
        {!areas.isLoading && !areas.isError && !globalRows.length ? <EmptyState title="No Principle packages found"><p>Configure a shared principle-packages directory or add a catalog. Private Principles remain isolated to this working directory.</p></EmptyState> : null}
        <div className="area-grid">{globalRows.map((areaObject) => {
          const area = textValue(areaObject.area);
          const displayName = textValue(areaObject.display_name, area);
          const version = textValue(areaObject.package_version);
          const installed = Boolean(areaObject.installed);
          const pinned = Boolean(areaObject.pinned);
          const unassessed = textValue(areaObject.content_class) === "unassessed_candidates";
          return <article className="area-card compact" key={`${area}-${version}`}>
            <div className="card-top"><span className="area-icon">{displayName.slice(0, 2).toUpperCase()}</span><span className={`pill ${installed ? "success" : ""}`}>{installed ? "Installed locally" : "Available"}</span></div>
            <h2>{displayName}</h2><p className="muted">{area}</p>
            <p className="package-content-notice">{unassessed ? "Public literature · Automated evidence checks passed · Human review pending · Paper files not included" : "Human-reviewed Principle Capsules · Paper files not included"}</p>
            <dl><div><dt>Version</dt><dd>{version || "—"}</dd></div><div><dt>Principles</dt><dd>{numberValue(areaObject.principle_count)}</dd></div><div><dt>Relations</dt><dd>{numberValue(areaObject.relation_count)}</dd></div><div><dt>Integrity</dt><dd>{textValue(areaObject.integrity, "Catalog")}</dd></div></dl>
              <div className="card-actions">{installed ? <><button onClick={() => navigate(`/map?scope=global&package=${encodeURIComponent(area)}`)}>Open Explorer</button><button onClick={() => packageAction.mutate({ area, action: "verify", version })}>Verify</button><button aria-pressed={pinned} onClick={() => packageAction.mutate({ area, action: "pin", version, pinned: !pinned })}>{pinned ? "Unpin" : "Pin"}</button><button onClick={() => packageAction.mutate({ area, action: "rollback" })}>Rollback</button></> : <button className="primary" onClick={() => packageAction.mutate({ area, action: "install", version })}>Install</button>}</div>
          </article>;
        })}</div>
      </div>
    </details>
    {packageAction.isPending ? <div className="toast" role="status">Verifying and activating package…</div> : null}
  </div>;
}
