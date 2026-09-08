import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
import { PageHeader } from "../components/Shell";
import { SmartSelect } from "../components/SmartSelect";
import { downloadJson } from "../utils/export";

type PrincipleCard = components["schemas"]["PrincipleCardResponse"];
type PrinciplePage = components["schemas"]["PrincipleCardPage"];
type PrincipleGraphView = components["schemas"]["PrincipleGraphViewResponse"];
type PotentialRelationsResponse = components["schemas"]["PotentialRelationsResponse"];
type Collection = components["schemas"]["LibraryCollectionItem"];
type ObjectValue = { [key: string]: unknown };

const PrincipleGraph = lazy(() => import("../components/PrincipleGraph").then((module) => ({ default: module.PrincipleGraph })));

const claimLabels: { [key: string]: string } = {
  empirical_association: "Observed relationship",
  causal_mechanism: "Causal or mechanistic claim",
  design_rule_or_intervention: "Intervention or design rule",
  boundary_or_tradeoff: "Boundary or trade-off",
  formal_proposition: "Formal or theoretical result",
  empirical: "Empirical",
  mechanistic: "Mechanistic",
  heuristic: "Design heuristic",
  theorem: "Formal result",
};

const evidenceLabels = {
  checks_passed: "Evidence checks passed",
  checking: "Checking evidence",
  held_back: "Held back",
  update_required: "Needs updated evidence checks",
  archived: "Archived",
};

function objectValue(value: unknown): ObjectValue {
  return value !== null && typeof value === "object" ? value as ObjectValue : {};
}

function textValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function listValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function countMap(value: unknown): { [key: string]: number } {
  const record = objectValue(value);
  return Object.fromEntries(Object.entries(record).map(([key, count]) => [key, Number(count) || 0]));
}

function Score({ label, score, first, second, help }: {
  label: string;
  score: number | null | undefined;
  first: string;
  second: string;
  help: string;
}) {
  return <div className="relation-score" title={help}>
    <span>{label}</span><strong>{score === null || score === undefined ? "—" : `${score.toFixed(0)}`}</strong>
    <small>{score === null || score === undefined ? "Not enough validated relations" : `${first} · ${second}`}</small>
  </div>;
}

export function MapPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const searchInput = useRef<HTMLInputElement | null>(null);
  const [queryInput, setQueryInput] = useState(params.get("q") ?? "");
  const scope = params.get("scope") === "global" || params.get("scope") === "combined" ? params.get("scope")! : "local";
  const area = params.get("area") ?? "";
  const packageId = params.get("package") ?? "";
  const goalId = params.get("goal") ?? "";
  const sourceId = params.get("source") ?? "";
  const goalRunId = params.get("goal_run") ?? "";
  const latestGoalRun = useQuery({
    queryKey: ["research-goal-run", "latest"],
    enabled: !goalRunId,
    queryFn: async () => objectValue(dataOrThrow(await api.GET("/api/v1/research-goal-runs/latest", {}))),
  });
  useEffect(() => {
    const latestId = textValue(latestGoalRun.data?.run_id);
    if (!goalRunId && latestId) {
      navigate(`/map?scope=combined&goal_run=${encodeURIComponent(latestId)}`, { replace: true });
    }
  }, [goalRunId, latestGoalRun.data?.run_id, navigate]);
  const pageNumber = Math.max(1, Number(params.get("page") ?? 1) || 1);
  const selectedId = params.get("selected") ?? params.get("seed") ?? "";
  const q = params.get("q") ?? "";
  const sort = params.get("sort") ?? (q ? "relevance" : "updated");
  const claimType = params.get("claim_type") ?? "";
  const evidenceStatus = params.get("evidence") ?? "checks_passed";
  const humanReview = params.get("review") ?? "";
  const minimumSupport = Number(params.get("support") ?? 0);
  const relationFilter = params.get("relations") ?? "";
  const contradictions = params.get("contradictions") === "true" ? true : undefined;
  const scenarioMode = params.get("scenario") === "true";
  const graphMode = params.get("view") === "graph";
  const scenarioId = params.get("scenario_id") ?? "";
  const [virtualTitle, setVirtualTitle] = useState("");
  const [virtualClaim, setVirtualClaim] = useState("");
  const [scenarioDiff, setScenarioDiff] = useState<ObjectValue | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const goalRun = useQuery({
    queryKey: ["research-goal-run", goalRunId],
    enabled: Boolean(goalRunId),
    queryFn: async () => objectValue(dataOrThrow(await api.GET("/api/v1/research-goal-runs/{run_id}", { params: { path: { run_id: goalRunId } } }))),
    refetchInterval: (query) => ["succeeded", "partial", "failed", "cancelled", "interrupted"].includes(textValue(objectValue(query.state.data).state)) ? false : 750,
  });
  const goalMembershipCounts = useQuery({
    queryKey: ["research-goal-membership-counts", goalRunId],
    enabled: Boolean(goalRunId),
    refetchInterval: ["succeeded", "partial", "failed", "cancelled", "interrupted"].includes(textValue(goalRun.data?.state)) ? false : 1_000,
    queryFn: async () => Object.fromEntries(await Promise.all((["combined", "global", "local"] as const).map(async (membership) => {
      const value = dataOrThrow(await api.GET("/api/v1/research-goal-runs/{run_id}/results", { params: { path: { run_id: goalRunId }, query: { membership, limit: 1, offset: 0 } } }));
      return [membership, value.total] as const;
    }))),
  });

  const updateParams = (updates: { [key: string]: string | null }, replace = false) => {
    const next = new URLSearchParams(params);
    Object.entries(updates).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    const preservesCurrentPage = Object.keys(updates).every((key) =>
      ["selected", "scenario", "scenario_id"].includes(key)
    );
    if (!("page" in updates) && !preservesCurrentPage) next.delete("page");
    next.delete("seed");
    setParams(next, { replace });
  };

  const principlePage = useQuery({
    queryKey: ["principle-cards", scope, goalRunId, q, area, packageId, goalId, sourceId, claimType, evidenceStatus, humanReview, minimumSupport, relationFilter, contradictions, sort, pageNumber],
    placeholderData: (previous) => previous,
    refetchInterval: goalRunId && !["succeeded", "partial", "failed", "cancelled", "interrupted"].includes(textValue(goalRun.data?.state)) ? 1_250 : false,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/principles", {
      params: { query: {
        scope: scope as "local" | "global" | "combined",
        q,
        area,
        package_id: packageId,
        goal_id: goalId,
        source_id: sourceId,
        goal_run_id: goalRunId,
        claim_type: claimType,
        evidence_status: evidenceStatus,
        human_review: humanReview,
        minimum_supporting_papers: minimumSupport,
        has_reliability: relationFilter === "reliability" ? true : undefined,
        has_influence: relationFilter === "influence" ? true : undefined,
        known_contradictions: contradictions,
        sort: sort as "relevance" | "updated" | "reliability" | "influence" | "supporting_papers" | "title",
        limit: 24,
        page: pageNumber,
      } },
    })) as PrinciplePage,
  });
  const cards = principlePage.data?.items ?? [];
  const firstPage = principlePage.data;
  const graphView = useQuery({
    queryKey: ["principle-graph", scope, goalRunId, q, area, packageId, goalId, sourceId, claimType, evidenceStatus, humanReview, minimumSupport, relationFilter, contradictions, sort],
    enabled: graphMode,
    placeholderData: (previous) => previous,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/principles/graph", {
      params: { query: {
        scope: scope as "local" | "global" | "combined",
        q,
        area,
        package_id: packageId,
        goal_id: goalId,
        source_id: sourceId,
        goal_run_id: goalRunId,
        claim_type: claimType,
        evidence_status: evidenceStatus,
        human_review: humanReview,
        minimum_supporting_papers: minimumSupport,
        has_reliability: relationFilter === "reliability" ? true : undefined,
        has_influence: relationFilter === "influence" ? true : undefined,
        known_contradictions: contradictions,
        sort: sort as "relevance" | "updated" | "reliability" | "influence" | "supporting_papers" | "title",
        limit: 120,
      } },
    })) as PrincipleGraphView,
  });
  const graphCards = graphView.data?.nodes ?? [];
  const contextualFacets = useQuery({
    queryKey: ["principle-facets", scope, q, packageId, goalId, sourceId],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/principles", {
      params: { query: {
        scope: scope as "local" | "global" | "combined",
        q,
        area: "",
        package_id: packageId,
        goal_id: goalId,
        source_id: sourceId,
        claim_type: "",
        evidence_status: "",
        human_review: "",
        minimum_supporting_papers: 0,
        sort: q ? "relevance" : "updated",
        limit: 1,
        page: 1,
      } },
    })) as PrinciplePage,
  });
  const viewFacets = useQuery({
    queryKey: ["principle-view-facets", scope, q, packageId, goalId, sourceId, claimType, evidenceStatus, humanReview, minimumSupport, relationFilter, contradictions],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/principles", {
      params: { query: {
        scope: scope as "local" | "global" | "combined",
        q,
        area: "",
        package_id: packageId,
        goal_id: goalId,
        source_id: sourceId,
        claim_type: claimType,
        evidence_status: evidenceStatus,
        human_review: humanReview,
        minimum_supporting_papers: minimumSupport,
        has_reliability: relationFilter === "reliability" ? true : undefined,
        has_influence: relationFilter === "influence" ? true : undefined,
        known_contradictions: contradictions,
        sort: q ? "relevance" : "updated",
        limit: 1,
        page: 1,
      } },
    })) as PrinciplePage,
  });
  const claimFacets = useQuery({
    queryKey: ["principle-claim-facets", scope, q, area, packageId, goalId, sourceId, evidenceStatus, humanReview, minimumSupport, relationFilter, contradictions],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/principles", {
      params: { query: {
        scope: scope as "local" | "global" | "combined",
        q,
        area,
        package_id: packageId,
        goal_id: goalId,
        source_id: sourceId,
        claim_type: "",
        evidence_status: evidenceStatus,
        human_review: humanReview,
        minimum_supporting_papers: minimumSupport,
        has_reliability: relationFilter === "reliability" ? true : undefined,
        has_influence: relationFilter === "influence" ? true : undefined,
        known_contradictions: contradictions,
        sort: q ? "relevance" : "updated",
        limit: 1,
        page: 1,
      } },
    })) as PrinciplePage,
  });

  const goals = useQuery({
    queryKey: ["explorer-goals"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/library/collections", { params: { query: { kind: "research_goal" } } })),
  });
  const folders = useQuery({
    queryKey: ["explorer-folders"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/library/collections", { params: { query: { kind: "source" } } })),
  });
  const areas = useQuery({
    queryKey: ["explorer-areas"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/library/collections", { params: { query: { kind: "area" } } })),
  });
  const packages = useQuery({
    queryKey: ["explorer-packages"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/areas", {})),
  });
  const detail = useQuery({
    queryKey: ["principle-detail", selectedId],
    enabled: Boolean(selectedId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/principles/{principle_id}", { params: { path: { principle_id: selectedId } } })),
  });
  const relations = useQuery({
    queryKey: ["principle-relations", selectedId],
    enabled: Boolean(selectedId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/principles/{principle_id}/relations", { params: { path: { principle_id: selectedId } } })),
  });
  const selectedCard = [...cards, ...graphCards].find((card) => card.id === selectedId);
  const detailValue = objectValue(detail.data);
  const argument = objectValue(detailValue.scientific_argument);
  const evidence = [
    ...listValue(detailValue.evidence),
    ...listValue(detailValue.source_references),
  ].map(objectValue);
  const relationRows = relations.data?.items ?? [];

  const scenarios = useQuery({
    queryKey: ["scenarios"],
    enabled: scenarioMode,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/scenarios", {})),
  });
  const scenarioRows = listValue(objectValue(scenarios.data).scenarios).map(objectValue);
  const createScenario = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/scenarios", { body: { name: `Explorer scenario ${new Date().toLocaleString()}`, parent_scenario_id: null } })),
    onSuccess: (value) => updateParams({ scenario: "true", scenario_id: textValue(objectValue(value).scenario_id) }),
  });
  const addVirtual = useMutation({
    mutationFn: async () => {
      await dataOrThrow(await api.POST("/api/v1/scenarios/{scenario_id}/events", { params: { path: { scenario_id: scenarioId } }, body: { event_type: "add_virtual_principle", payload: { title: virtualTitle, claim: virtualClaim } } }));
      return dataOrThrow(await api.GET("/api/v1/scenarios/{scenario_id}/diff", { params: { path: { scenario_id: scenarioId } } }));
    },
    onSuccess: (value) => { setScenarioDiff(objectValue(value)); setVirtualTitle(""); setVirtualClaim(""); },
  });
  const editPrinciple = useMutation({
    mutationFn: async () => dataOrThrow(await api.PATCH("/api/v1/local/candidates/{candidate_id}", { params: { path: { candidate_id: selectedId } }, body: { title: editingTitle } })),
    onSuccess: () => { setEditingTitle(""); queryClient.invalidateQueries({ queryKey: ["principle-cards"] }); queryClient.invalidateQueries({ queryKey: ["principle-detail", selectedId] }); },
  });
  const archivePrinciple = useMutation({
    mutationFn: async () => dataOrThrow(await api.DELETE("/api/v1/local/candidates/{candidate_id}", { params: { path: { candidate_id: selectedId } } })),
    onSuccess: () => { updateParams({ selected: null }); queryClient.invalidateQueries({ queryKey: ["principle-cards"] }); },
  });
  const restorePrinciple = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/local/candidates/{candidate_id}/restore", { params: { path: { candidate_id: selectedId } } })),
    onSuccess: () => { updateParams({ evidence: "checks_passed", selected: null }); queryClient.invalidateQueries({ queryKey: ["principle-cards"] }); },
  });
  const analyzePotentialRelations = async (principleIds: string[]): Promise<PotentialRelationsResponse> =>
    dataOrThrow(await api.POST("/api/v1/principles/potential-relations", {
      body: { principle_ids: principleIds },
    }));

  useEffect(() => {
    if (!selectedId) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") updateParams({ selected: null });
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [selectedId, params]);

  const goalRows: Collection[] = goals.data?.items ?? [];
  const folderRows: Collection[] = folders.data?.items ?? [];
  const areaRows: Collection[] = areas.data?.items ?? [];
  const facetValue = objectValue(contextualFacets.data?.facets);
  const viewFacetValue = objectValue(viewFacets.data?.facets);
  const claimFacetValue = objectValue(claimFacets.data?.facets);
  const mainFacetValue = objectValue(firstPage?.facets);
  const areaCounts = countMap(viewFacetValue.area_counts);
  const contextualAreaCounts = countMap(facetValue.area_counts);
  const claimTypeCounts = countMap(claimFacetValue.claim_type_counts);
  const evidenceStatusCounts = countMap(facetValue.evidence_status_counts);
  const humanReviewCounts = countMap(facetValue.human_review_status_counts);
  const reliabilityAvailable = Number(mainFacetValue.reliability_available_count) || 0;
  const influenceAvailable = Number(mainFacetValue.influence_available_count) || 0;
  const contradictionCount = Number(mainFacetValue.known_contradiction_count) || 0;
  const localAreaById = new Map(areaRows.map((item) => [item.area, item]));
  const explorerAreaIds = [...new Set(
    scope === "local"
      ? areaRows.map((item) => item.area)
      : scope === "global"
        ? Object.keys(contextualAreaCounts)
        : [...areaRows.map((item) => item.area), ...Object.keys(contextualAreaCounts)],
  )].filter(Boolean).sort((left, right) => left.localeCompare(right));
  const areaFiltersAreNarrowed = Boolean(
    q
    || goalId
    || sourceId
    || claimType
    || evidenceStatus !== "checks_passed"
    || humanReview
    || minimumSupport
    || relationFilter
    || contradictions,
  );
  const explorerAreaOptions = explorerAreaIds.map((areaId) => {
    const libraryArea = localAreaById.get(areaId);
    const libraryCount = libraryArea?.principle_count;
    const contextualCount = contextualAreaCounts[areaId] ?? libraryCount ?? 0;
    const matchingCount = areaCounts[areaId] ?? 0;
    const totalDescription = scope === "local" && libraryCount !== undefined
      ? `${libraryCount} ready to review in Principles Library`
      : `${contextualCount} in ${scope === "global" ? "Global" : "Combined"} knowledge`;
    return {
      value: areaId,
      label: (libraryArea?.title ?? areaId).replaceAll("-", " "),
      description: areaFiltersAreNarrowed || matchingCount !== contextualCount
        ? `${matchingCount} match current filters · ${totalDescription}`
        : totalDescription,
      disabled: matchingCount === 0 && areaId !== area,
    };
  });
  const activeGoal = goalRows.find((item) => item.collection_id === goalId);
  const activeFolder = folderRows.find((item) => item.source_id === sourceId);
  const activeArea = areaRows.find((item) => item.area === area);
  const activePackage = listValue(objectValue(packages.data).areas)
    .map(objectValue)
    .find((item) => textValue(item.area) === packageId);
  const collectionTitle = goalRunId ? textValue(goalRun.data?.goal, "Research goal results") : activeGoal?.title
    ?? activeFolder?.title
    ?? (activeArea ? `${activeArea.title.replaceAll("-", " ")} Principles` : undefined)
    ?? (activePackage ? `${textValue(activePackage.display_name, packageId)} Principles` : "All Principles");
  const collectionDescription = activeGoal
    ? `Principles grounded in papers collected for this research question. The question is fixed by the Library collection, not used as an extra Explorer filter.`
    : activeFolder
      ? `Principles extracted from papers indexed in the private folder “${activeFolder.title}”.`
      : activeArea
        ? `Principles currently organized under the ${activeArea.title.replaceAll("-", " ")} Area label.`
        : activePackage
          ? `A verified local copy of the ${textValue(activePackage.display_name, packageId)} downloadable package. Paper files are excluded; public source links remain available.`
        : "Browse the complete installed Principle library with explicit scientific and evidence filters.";
  const metricState = textValue(objectValue(firstPage?.metric_status).state, "not_built");
  const visibleDescription = graphMode
    ? (graphView.data ? `${graphView.data.shown_count} of ${graphView.data.total_count}` : "—")
    : (firstPage ? `${cards.length} of ${firstPage.total}` : "—");

  return <div className="page explorer-page">
    <PageHeader
      eyebrow={goalRunId ? "Reproducible research-goal result" : scope === "global" ? "Downloaded scientific knowledge" : scope === "combined" ? "Private and downloaded scientific knowledge" : "Private scientific knowledge"}
      title={collectionTitle}
      description={goalRunId ? "Principles found for this goal. Switch between Combined, Global, and Local without rerunning the search." : collectionDescription}
      actions={<><button className={graphMode ? "primary" : ""} aria-pressed={graphMode} onClick={() => updateParams({ view: graphMode ? null : "graph", selected: null })}>{graphMode ? "Card Mode" : "Graph Mode"}</button>{goalRunId ? <button onClick={() => downloadJson("principia-goal-results", { goal_run: goalRun.data, membership: scope, cards: graphMode ? graphCards : cards, relations: graphView.data?.edges ?? [] })}>Export results</button> : <><button aria-pressed={scenarioMode} onClick={() => updateParams({ scenario: scenarioMode ? null : "true" })}>Scenario Mode</button><button onClick={() => downloadJson("principia-explorer", { filters: Object.fromEntries(params), cards: graphMode ? graphCards : cards, relations: graphView.data?.edges ?? [] })}>Export view</button></>}</>}
    />

    {goalRunId ? <nav className="goal-membership-tabs" aria-label="Research goal result source">{(["combined", "global", "local"] as const).map((membership) => <button key={membership} className={scope === membership ? "selected" : ""} aria-pressed={scope === membership} onClick={() => updateParams({ scope: membership, selected: null })}><strong>{membership === "combined" ? "Combined" : membership === "global" ? "Global" : "Local"}</strong><small>{String(goalMembershipCounts.data?.[membership] ?? "—")} Principles</small></button>)}</nav> : <section className="explorer-context" aria-label="Explorer context">
      <div><strong>{visibleDescription}</strong><span>Principles shown</span></div>
      <div><strong>{firstPage?.total ?? "—"}</strong><span>Matching this view</span></div>
      <p>{graphMode ? "Each node is one Principle; arrows are validated scientific relations. Filters and search update both Explorer views." : "Each card is one evidence-grounded Principle argument. Reliability and Influence appear only when validated relations exist."}</p>
    </section>}

    {scenarioMode ? <section className="scenario-card-panel">
      <div><span className="eyebrow">Reversible workspace</span><h2>Scenario Mode</h2><p>Virtual Principles and edits stay outside canonical knowledge.</p></div>
      <label><span>Scenario</span><SmartSelect ariaLabel="Scenario" value={scenarioId} onChange={(value) => updateParams({ scenario_id: value })} placeholder="Choose a scenario…" options={scenarioRows.map((row) => ({ value: textValue(row.scenario_id), label: textValue(row.name) }))} /></label>
      {!scenarioId ? <button className="primary" onClick={() => createScenario.mutate()}>Create scenario</button> : <><label><span>Virtual Principle title</span><input value={virtualTitle} onChange={(event) => setVirtualTitle(event.target.value)} /></label><label><span>Scenario-only claim</span><input value={virtualClaim} onChange={(event) => setVirtualClaim(event.target.value)} /></label><button onClick={() => addVirtual.mutate()} disabled={!virtualTitle.trim() || !virtualClaim.trim()}>Add virtual card</button></>}
      {scenarioDiff ? <details className="scenario-diff"><summary>Scenario diff</summary><pre>{JSON.stringify(scenarioDiff, null, 2)}</pre></details> : null}
    </section> : null}

    <div className={`explorer-shell ${goalRunId ? "goal-run-explorer" : ""}`}>
      {(() => { const FiltersContainer: "details" | "aside" = goalRunId ? "details" : "aside"; return <FiltersContainer className="explorer-filters" aria-label="Principle filters">
        {goalRunId ? <summary>Refine these results</summary> : null}
        <h2>Filter Principles</h2>
        {!goalRunId ? <label><span>Knowledge source</span><SmartSelect ariaLabel="Knowledge source" value={scope} onChange={(value) => updateParams({ scope: value, selected: null })} options={[{ value: "local", label: "Local" }, { value: "global", label: "Global" }, { value: "combined", label: "Combined" }]} /></label> : null}
        <label><span>Area</span><SmartSelect ariaLabel="Area" value={area} onChange={(value) => updateParams({ area: value, selected: null })} options={[{ value: "", label: "All Areas", description: `${viewFacets.data?.total ?? 0} Principles match current filters` }, ...explorerAreaOptions]} /></label>
        <p className="filter-help">These are the same Areas shown in Principles Library. A Principle may belong to more than one Area.</p>
        {activeGoal ? <div className="collection-filter-context"><span>Library collection</span><strong>{activeGoal.title}</strong><button onClick={() => updateParams({ goal: null, selected: null })}>View all Principles</button></div> : null}
        <label><span>Private folder</span><SmartSelect ariaLabel="Private folder" value={sourceId} onChange={(value) => updateParams({ source: value, selected: null })} options={[{ value: "", label: "All folders" }, ...folderRows.map((item) => ({ value: item.source_id, label: item.title, description: `${item.work_count} documents` }))]} /></label>
        <label><span>Claim type</span><SmartSelect ariaLabel="Claim type" value={claimType} onChange={(value) => updateParams({ claim_type: value, selected: null })} options={[{ value: "", label: "All claim types", description: `${claimFacets.data?.total ?? 0} Principles` }, ...Object.entries(claimLabels).slice(0, 5).filter(([value]) => claimTypeCounts[value] > 0 || value === claimType).map(([value, label]) => ({ value, label, description: `${claimTypeCounts[value] ?? 0} Principles` }))]} /></label>
        <label><span>Evidence status</span><SmartSelect ariaLabel="Evidence status" value={evidenceStatus} onChange={(value) => updateParams({ evidence: value, selected: null })} options={[{ value: "", label: "All states", description: `${contextualFacets.data?.total ?? 0} in this collection` }, ...([{ value: "checks_passed", label: "Ready to review" }, { value: "checking", label: "Checking evidence" }, { value: "held_back", label: "Held back" }, { value: "update_required", label: "Needs updated checks" }, { value: "archived", label: "Archived" }]).filter((item) => evidenceStatusCounts[item.value] > 0 || item.value === evidenceStatus).map((item) => ({ ...item, description: item.value === evidenceStatus ? `${firstPage?.total ?? 0} matching` : `${evidenceStatusCounts[item.value] ?? 0} in this collection` }))]} /></label>
        <label><span>Human review</span><SmartSelect ariaLabel="Human review" value={humanReview} onChange={(value) => updateParams({ review: value, selected: null })} options={[{ value: "", label: "Any review state", description: `${firstPage?.total ?? 0} matching` }, ...([{ value: "pending", label: "Review pending" }, { value: "reviewed", label: "Human reviewed" }, { value: "rejected", label: "Rejected" }]).filter((item) => humanReviewCounts[item.value] > 0 || item.value === humanReview).map((item) => ({ ...item, description: item.value === humanReview ? `${firstPage?.total ?? 0} matching` : `${humanReviewCounts[item.value] ?? 0} in this collection` }))]} /></label>
        <label><span>Minimum supporting papers</span><input type="number" min={0} value={minimumSupport} onChange={(event) => updateParams({ support: event.target.value === "0" ? null : event.target.value, selected: null })} /></label>
        <label><span>Relation evidence</span><SmartSelect ariaLabel="Relation evidence" value={relationFilter} onChange={(value) => updateParams({ relations: value, selected: null })} options={[{ value: "", label: "Any availability", description: `${firstPage?.total ?? 0} matching` }, ...(reliabilityAvailable || relationFilter === "reliability" ? [{ value: "reliability", label: "Reliability available", description: `${reliabilityAvailable} matching` }] : []), ...(influenceAvailable || relationFilter === "influence" ? [{ value: "influence", label: "Influence available", description: `${influenceAvailable} matching` }] : [])]} /></label>
        <label className="inline-check"><input type="checkbox" checked={Boolean(contradictions)} disabled={!contradictionCount && !contradictions} onChange={(event) => updateParams({ contradictions: event.target.checked ? "true" : null, selected: null })} /><span>{contradictionCount ? `Known contradictions only (${contradictionCount})` : "No validated contradictions"}</span></label>
        <button onClick={() => { const reset = new URLSearchParams({ scope, evidence: "checks_passed" }); if (packageId) reset.set("package", packageId); if (goalId) reset.set("goal", goalId); if (sourceId) reset.set("source", sourceId); if (activeArea) reset.set("area", area); setParams(reset); }}>Reset filters</button>
      </FiltersContainer>; })()}

      <main className="explorer-results">
        <div className="explorer-toolbar">
          <form onSubmit={(event) => { event.preventDefault(); updateParams({ q: queryInput.trim() || null, sort: queryInput.trim() ? "relevance" : "updated", selected: null }); }}><input ref={searchInput} value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Search claims, mechanisms, interventions, or boundaries…" aria-label="Search Principles" /><button className="primary">Search</button></form>
          <label><span className="sr-only">Sort Principles</span><SmartSelect ariaLabel="Sort Principles" value={sort} onChange={(value) => updateParams({ sort: value, selected: null })} options={[{ value: "relevance", label: "Best match" }, { value: "updated", label: "Recently updated" }, ...(reliabilityAvailable || sort === "reliability" ? [{ value: "reliability", label: "Reliability" }] : []), ...(influenceAvailable || sort === "influence" ? [{ value: "influence", label: "Influence" }] : []), { value: "supporting_papers", label: "Supporting papers" }, { value: "title", label: "Title" }]} /></label>
        </div>
        {goalRunId ? <details className="score-explanation compact"><summary>About Reliability and Influence</summary><span>Reliability summarizes validated support versus contradiction links using a conservative confidence bound. Influence is connectivity within this installed library. Neither is a truth probability or real-world importance score.</span>{metricState !== "complete" ? <em>Relation measures are not available yet.</em> : null}</details> : <div className="score-explanation"><strong>How these measures work</strong><span>Reliability summarizes validated support versus contradiction links using a conservative confidence bound. Influence is connectivity within this installed library. Neither is a truth probability or real-world importance score.</span>{metricState !== "complete" ? <em>Relation measures are not available yet.</em> : null}</div>}
        {(graphMode ? graphView.isLoading : principlePage.isLoading) ? <LoadingState label={graphMode ? "Laying out validated Principle relations…" : "Preparing Principle cards…"} /> : null}
        {(graphMode ? graphView.isError : principlePage.isError) ? <ErrorState error={graphMode ? graphView.error : principlePage.error} retry={() => graphMode ? graphView.refetch() : principlePage.refetch()} /> : null}
        {graphMode && graphView.data && graphCards.length ? <><div className="graph-view-heading"><div><strong>{graphView.data.shown_count} Principles · {graphView.data.edges.length} validated relations</strong><span>{graphView.data.explanation}</span></div>{graphView.data.truncated ? <em>Showing the first {graphView.data.maximum_nodes} matching Principles. Refine the view to focus the graph.</em> : null}</div><Suspense fallback={<LoadingState label="Loading the interactive graph surface…" />}><PrincipleGraph cards={graphCards} relations={graphView.data.edges} selectedId={selectedId} onSelectPrinciple={(id) => updateParams({ selected: id })} onAnalyzePotentialRelations={analyzePotentialRelations} /></Suspense></> : null}
        {!(graphMode ? graphView.isLoading : principlePage.isLoading) && !(graphMode ? graphView.isError : principlePage.isError) && !(graphMode ? graphCards.length : cards.length) ? <EmptyState title="No Principles match this view"><p>Try clearing a filter or inspect Held back drafts separately. Principia will not invent filler to populate the library.</p></EmptyState> : null}
        {!graphMode ? <section className="principle-card-grid" aria-label="Principle cards">{cards.map((card) => <article className={`principle-card ${selectedId === card.id ? "selected" : ""}`} key={card.id}>
          <button className="principle-card-open" onClick={() => updateParams({ selected: card.id })} aria-label={`Inspect ${card.title}`}>
            <div className="principle-card-top"><span className={`source-badge ${card.source}`}>{card.source === "local" ? "Local" : card.source === "both" ? "Global + Local" : "Global"}</span><span>{claimLabels[card.claim_type] ?? card.claim_type.replaceAll("_", " ")}</span></div>
            <h2>{card.title}</h2><p>{card.claim}</p>
          </button>
          <div className="principle-card-tags">{card.area_labels.length ? card.area_labels.map((label) => <span key={label}>{label.replaceAll("-", " ")}</span>) : <span>Not categorized</span>}<span>{evidenceLabels[card.evidence_status]}</span><span>{card.human_review_status === "pending" ? "Human review pending" : card.human_review_status}</span></div>
          <div className="principle-card-applicability"><strong>Applicability</strong><span>{card.applicability || "Open the evidence record for the reported conditions."}</span></div>
          <div className="principle-card-evidence"><strong>{card.supporting_work_count}</strong><span>supporting paper{card.supporting_work_count === 1 ? "" : "s"}</span><strong>{card.evidence_anchor_count}</strong><span>evidence anchor{card.evidence_anchor_count === 1 ? "" : "s"}</span></div>
          <div className="principle-card-relations"><strong>Related Principles</strong>{(card.related_principles ?? []).length ? <ul>{(card.related_principles ?? []).map((related) => <li key={`${related.principle_id}:${related.relation_type}`}><button onClick={() => updateParams({ selected: related.principle_id })}><span>{related.relation_type.replaceAll("_", " ")}</span>{related.title}</button></li>)}</ul> : <span>No validated relation yet</span>}{(card.validated_relation_count ?? 0) > (card.related_principles ?? []).length ? <small>+{(card.validated_relation_count ?? 0) - (card.related_principles ?? []).length} more in details</small> : null}</div>
          <div className="principle-card-scores"><Score label="Reliability" score={card.reliability_score} first={`${card.incoming_support_count} supports`} second={`${card.incoming_contradict_count} contradicts`} help="A library-relative measure from validated incoming support and contradiction links; not a probability that the claim is true." /><Score label="Influence" score={card.influence_score} first={`${card.distinct_neighbor_count} neighbors`} second="installed library" help="Connectivity among validated scientific relations in this installed library; not real-world importance." /></div>
        </article>)}</section> : null}
        {!graphMode && firstPage && firstPage.page_count > 1 ? <nav className="principle-pagination" aria-label="Principle pages"><button disabled={pageNumber <= 1 || principlePage.isFetching} onClick={() => updateParams({ page: String(pageNumber - 1), selected: null })}>Previous</button><span>Page <strong>{pageNumber}</strong> of <strong>{firstPage.page_count}</strong></span><label><span className="sr-only">Go to page</span><input type="number" min={1} max={firstPage.page_count} value={pageNumber} onChange={(event) => { const requested = Math.max(1, Math.min(firstPage.page_count, Number(event.target.value) || 1)); updateParams({ page: String(requested), selected: null }); }} /></label><button disabled={pageNumber >= firstPage.page_count || principlePage.isFetching} onClick={() => updateParams({ page: String(pageNumber + 1), selected: null })}>Next</button></nav> : null}
      </main>
    </div>

    {selectedId ? <div className="detail-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) updateParams({ selected: null }); }}><aside className="principle-detail-drawer" role="dialog" aria-modal="true" aria-labelledby="principle-detail-title">
      <header><div><span className="eyebrow">{selectedCard?.source === "global" ? (selectedCard.human_review_status === "reviewed" ? "Reviewed package Principle" : "Downloaded Principle · Human review pending") : "Local Principle · Human review pending"}</span><h2 id="principle-detail-title">{selectedCard?.title ?? textValue(detailValue.title, "Opening Principle…")}</h2></div><button aria-label="Close Principle details" onClick={() => updateParams({ selected: null })}>×</button></header>
      {detail.isLoading ? <LoadingState label="Opening evidence and relations…" /> : null}
      {detail.isError ? <ErrorState error={detail.error} retry={() => detail.refetch()} /> : null}
      {!detail.isLoading && !detail.isError ? <div className="principle-detail-content">
        <p className="detail-claim">{textValue(detailValue.claim, selectedCard?.claim)}</p>
        <div className="detail-badges"><span>{selectedCard ? evidenceLabels[selectedCard.evidence_status] : "Evidence record"}</span><span>{selectedCard?.supporting_work_count ?? evidence.length} supporting paper{(selectedCard?.supporting_work_count ?? evidence.length) === 1 ? "" : "s"}</span><span>{selectedCard?.human_review_status === "reviewed" ? "Human reviewed" : "Human review pending"}</span></div>
        <section><h3>Applicability</h3><p>{listValue(argument.conditions).map(String).join("; ") || selectedCard?.applicability || textValue(objectValue(detailValue.scope).statement, "See source record.")}</p></section>
        <section><h3>Boundary</h3><p>{listValue(argument.boundary).map(String).join("; ") || listValue(detailValue.boundary).map(String).join("; ") || "The reported boundary has not been projected into this view."}</p></section>
        <section><h3>How it can be tested</h3><p>{textValue(argument.testability, textValue(detailValue.testability, textValue(detailValue.falsifier, "Human review is required to define a test.")))}</p></section>
        <section><h3>Validated relations</h3>{relations.isLoading ? <LoadingState label="Reading validated relations…" /> : relationRows.length ? <ul className="relation-list">{relationRows.map((relation) => <li key={relation.relation_id}><button onClick={() => updateParams({ selected: relation.related_principle_id })}><span>{relation.orientation === "incoming" ? "Incoming" : "Outgoing"} · {relation.relation_type.replaceAll("_", " ")}</span><strong>{relation.related_title}</strong></button><span>{relation.rationale}</span></li>)}</ul> : <p>No validated scientific relation is available. Proposed or shared-paper links are intentionally excluded.</p>}</section>
        <section><h3>Paper evidence</h3>{evidence.length ? <div className="evidence-cards">{evidence.map((item, index) => { const sourceUrl = textValue(item.source_url, textValue(item.url)); const quotation = textValue(item.quotation, textValue(item.excerpt)); return <article key={textValue(item.evidence_id, textValue(item.work_id, String(index)))}><strong>{textValue(item.work_title, textValue(item.title, "Supporting paper"))}</strong><small>{textValue(item.section)}{item.page_start ? ` · page ${String(item.page_start)}` : ""}</small>{quotation ? <blockquote>{quotation}</blockquote> : <p>Source text is not included in this portable package. The public paper link remains available.</p>}{sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer">Open source paper ↗</a> : <span>Public paper link unavailable</span>}</article>; })}</div> : <p>No public paper reference is projected for this Principle.</p>}</section>
        <details className="technical-record"><summary>Technical record</summary><pre>{JSON.stringify({ detail: detailValue, relations: relationRows, metric_revision: selectedCard?.metric_revision }, null, 2)}</pre></details>
        {selectedCard?.source === "local" ? <section className="principle-management"><h3>Manage this Principle</h3><p>Rename changes only the display title. Archiving hides the Principle without deleting its evidence or audit history.</p>{editingTitle ? <form onSubmit={(event) => { event.preventDefault(); editPrinciple.mutate(); }}><input autoFocus value={editingTitle} onChange={(event) => setEditingTitle(event.target.value)} /><button className="primary" disabled={editingTitle.trim().length < 3}>Save title</button><button type="button" onClick={() => setEditingTitle("")}>Cancel</button></form> : <div><button onClick={() => setEditingTitle(textValue(detailValue.title, selectedCard.title))}>Rename</button>{selectedCard.evidence_status === "archived" ? <button onClick={() => restorePrinciple.mutate()}>Restore</button> : <button onClick={() => { if (window.confirm("Archive this Principle? Its evidence and audit history will be preserved.")) archivePrinciple.mutate(); }}>Archive</button>}</div>}{editPrinciple.isError || archivePrinciple.isError || restorePrinciple.isError ? <ErrorState error={editPrinciple.error ?? archivePrinciple.error ?? restorePrinciple.error} /> : null}</section> : null}
        <div className="drawer-actions"><button onClick={() => downloadJson(`principia-${selectedId}`, detail.data)}>Export record</button><button className="primary" onClick={() => updateParams({ selected: null })}>Back to cards</button></div>
      </div> : null}
    </aside></div> : null}
  </div>;
}
