import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
import { JobProgress, terminalJobStates } from "../components/JobProgress";
import { PageHeader } from "../components/Shell";
import { SmartSelect } from "../components/SmartSelect";
import { downloadJson } from "../utils/export";

type LocalSource = components["schemas"]["LocalSourceResponse"];
type SourceDocument = components["schemas"]["SourceDocumentSummary"];
type Job = components["schemas"]["JobRecord"];
type StorageLayout = components["schemas"]["StorageLayoutDisclosureResponse"];
type Stage = "folder" | "papers" | "extract" | "results";
type ObjectValue = { [key: string]: unknown };

const stages: Array<{ id: Stage; label: string; helper: string }> = [
  { id: "folder", label: "Choose private folder", helper: "Connect or create a local evidence source" },
  { id: "papers", label: "Select papers", helper: "Index and choose the exact documents" },
  { id: "extract", label: "Extract reusable findings", helper: "Optional focus, provider, and safeguards" },
  { id: "results", label: "Review results", helper: "Inspect ready and held-back drafts" },
];

const reasonLabels: { [key: string]: string } = {
  document_meta_claim: "Describes the paper rather than a transferable scientific relationship",
  priority_or_novelty_claim: "Claims novelty or priority; this is metadata, not a reusable finding",
  author_self_claim: "Uses an author contribution claim as the scientific argument",
  descriptive_summary_not_principle: "Summarizes a study or method without a reusable argument",
  method_description_without_relation: "Names a method without an evidence-supported relationship or design rule",
  missing_argument_slot: "Missing a scientific subject, driver, outcome, condition, or boundary",
  unsupported_relationship: "The source does not support the relationship strength in the claim",
  unsupported_causal_language: "Uses causal language that the supplied evidence does not establish",
  unsupported_comparative_or_superlative: "Uses a comparison or superlative absent from the evidence",
  unsupported_generalization: "Generalizes beyond the supporting sources",
  unsupported_scope: "The applicability boundary does not match the evidence",
  non_falsifiable: "Does not provide a concrete way the claim could be tested",
  speculative_future_claim: "Makes a vague prediction about future importance instead of a testable scientific relationship",
  challenge_unavailable: "The second-pass evidence check could not be completed",
  challenge_inconclusive: "The second-pass evidence check did not support the draft",
};

function objectValue(value: unknown): ObjectValue {
  return value !== null && typeof value === "object" ? value as ObjectValue : {};
}

function textValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function listValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function reasons(value: string): string[] {
  return value.split(",").filter(Boolean).map((reason) => reasonLabels[reason] ?? reason.replaceAll("_", " "));
}

function searchWorkId(work: ObjectValue): string {
  return textValue(work.work_id, textValue(work.id));
}

function searchWorkUsable(work: ObjectValue): boolean {
  return Boolean(textValue(work.abstract).trim() || listValue(work.oa_locations).length);
}

function usableSelectedWorkIds(search: ObjectValue): string[] {
  const usable = new Set(listValue(search.results).map(objectValue).filter(searchWorkUsable).map(searchWorkId));
  return listValue(search.selected_work_ids).map(String).filter((workId) => usable.has(workId));
}

function defaultNewWorkIds(
  search: ObjectValue,
  existingWorkIds: Set<string>,
): string[] {
  const usable = new Set(listValue(search.results).map(objectValue).filter(searchWorkUsable).map(searchWorkId));
  const ordered = [
    ...listValue(search.selected_work_ids).map(String),
    ...listValue(search.alternate_work_ids).map(String),
    ...listValue(search.results).map(objectValue).map(searchWorkId),
  ];
  const target = Math.max(1, numberValue(search.target_count) || 20);
  return Array.from(new Set(ordered))
    .filter((workId) => usable.has(workId) && !existingWorkIds.has(workId))
    .slice(0, target);
}

function paperLabel(count: number): string {
  return `${count} paper${count === 1 ? "" : "s"}`;
}

function fileSizeLabel(bytes: number): string {
  if (!bytes) return "Size unavailable";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
}

function localDataFolderName(query: string): string {
  const slug = query.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 56);
  return slug || "public-literature";
}

function publicationLabel(work: ObjectValue): string {
  const venue = textValue(work.publication_venue);
  const listedVenue = textValue(work.venue);
  const status = textValue(work.publication_status);
  if (status === "published" && venue) return `Published in ${venue}`;
  if (status === "preprint") {
    if (listedVenue && !/^(arxiv|openreview|semantic scholar|crossref)$/i.test(listedVenue)) {
      return `OpenReview record · ${listedVenue}`;
    }
    const repository = /arxiv/i.test(listedVenue) ? "arXiv" : /openrxiv/i.test(listedVenue) ? "openRxiv" : /openreview/i.test(listedVenue) ? "OpenReview" : "repository copy";
    return `Preprint · ${repository}`;
  }
  return `Publication venue not confirmed · indexed by ${textValue(work.source, "scholarly provider")}`;
}

async function copyText(value: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value);
    return;
  } catch {
    const fallback = document.createElement("textarea");
    fallback.value = value;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.appendChild(fallback);
    fallback.select();
    const copied = document.execCommand("copy");
    fallback.remove();
    if (!copied) throw new Error("clipboard unavailable");
  }
}

export function LocalPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const requestedStage = params.get("stage");
  const stage: Stage = requestedStage === "papers" || requestedStage === "extract" || requestedStage === "results" ? requestedStage : "folder";
  const activeSourceId = params.get("source") ?? "";
  const [managedName, setManagedName] = useState("");
  const [manualPath, setManualPath] = useState("");
  const [createdLocation, setCreatedLocation] = useState("");
  const [documentQuery, setDocumentQuery] = useState("");
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [researchFocus, setResearchFocus] = useState("");
  const [model, setModel] = useState("deepseek-ai/DeepSeek-V4-Flash");
  const [policy, setPolicy] = useState<"remote" | "no_llm">("remote");
  const [confirmEgress, setConfirmEgress] = useState(false);
  const [credential, setCredential] = useState("");
  const [credentialMessage, setCredentialMessage] = useState("");
  const [pathMessage, setPathMessage] = useState("");
  const [indexJobId, setIndexJobId] = useState("");
  const [activeJobId, setActiveJobId] = useState(params.get("job") ?? "");
  const [resultView, setResultView] = useState<"eligible" | "quarantined">("eligible");

  useEffect(() => {
    const requestedJobId = params.get("job") ?? "";
    if (requestedJobId !== activeJobId) setActiveJobId(requestedJobId);
  }, [params, activeJobId]);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [newArea, setNewArea] = useState("");
  const [literatureOpen, setLiteratureOpen] = useState(false);
  const [searchQuestion, setSearchQuestion] = useState("");
  const [semanticRanking, setSemanticRanking] = useState(true);
  const [targetCount, setTargetCount] = useState(20);
  const [activeSearchId, setActiveSearchId] = useState("");
  const [pendingSearchId, setPendingSearchId] = useState("");
  const [searchJobId, setSearchJobId] = useState("");
  const [selectedWorkIds, setSelectedWorkIds] = useState<string[]>([]);
  const [acquisitionSourceId, setAcquisitionSourceId] = useState("");
  const [destinationMode, setDestinationMode] = useState<"existing" | "new">("new");
  const [destinationSourceId, setDestinationSourceId] = useState("");
  const [acquisitionFolderName, setAcquisitionFolderName] = useState("public-literature");
  const [acquisitionJobId, setAcquisitionJobId] = useState("");
  const [acquisitionReceipt, setAcquisitionReceipt] = useState<ObjectValue | null>(null);
  const automaticallyIndexed = useRef(new Set<string>());

  const setStage = (nextStage: Stage, sourceId = activeSourceId, jobId = activeJobId) => {
    const next = new URLSearchParams(params);
    next.set("stage", nextStage);
    sourceId ? next.set("source", sourceId) : next.delete("source");
    jobId ? next.set("job", jobId) : next.delete("job");
    setParams(next);
  };

  const openLiteratureForFolder = (sourceId = activeSourceId) => {
    if (sourceId) {
      setDestinationMode("existing");
      setDestinationSourceId(sourceId);
    }
    setLiteratureOpen(true);
  };

  const sources = useQuery({
    queryKey: ["local-sources"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/sources", {})),
  });
  const storageLayout = useQuery({
    queryKey: ["storage-layout"],
    queryFn: async () => dataOrThrow(await api.POST("/api/v1/local/storage-layout/disclosure", {})) as StorageLayout,
  });
  const sourceRows: LocalSource[] = sources.data?.sources ?? [];
  const pathDisclosures = useQuery({
    queryKey: ["source-paths", sourceRows.map((source) => source.source_id).join("|")],
    enabled: sourceRows.length > 0,
    queryFn: async () => dataOrThrow(await api.POST("/api/v1/local/sources/location-disclosures", { body: { source_ids: sourceRows.map((source) => source.source_id) } })),
  });
  const locationRows = listValue(objectValue(pathDisclosures.data).items).map(objectValue);
  const locations = useMemo(() => new Map(locationRows.map((item) => [textValue(item.source_id), item])), [pathDisclosures.data]);
  const picker = useQuery({
    queryKey: ["folder-picker"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/folder-picker", {})),
  });
  const sourceDetail = useQuery({
    queryKey: ["local-source", activeSourceId],
    enabled: Boolean(activeSourceId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/sources/{source_id}", { params: { path: { source_id: activeSourceId } } })),
  });
  const documents = useQuery({
    queryKey: ["source-documents", activeSourceId],
    enabled: Boolean(activeSourceId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/sources/{source_id}/documents", { params: { path: { source_id: activeSourceId }, query: { q: "", limit: 100, cursor: "" } } })),
  });
  const allDocumentRows: SourceDocument[] = documents.data?.items ?? [];
  const destinationDocuments = useQuery({
    queryKey: ["acquisition-destination-documents", destinationSourceId],
    enabled: literatureOpen && destinationMode === "existing" && Boolean(destinationSourceId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/sources/{source_id}/documents", { params: { path: { source_id: destinationSourceId }, query: { q: "", limit: 100, cursor: "" } } })),
  });
  const destinationWorkIds = useMemo(
    () => new Set((destinationDocuments.data?.items ?? []).map((document) => document.work_id)),
    [destinationDocuments.data],
  );
  const documentRows = useMemo(() => {
    const query = documentQuery.trim().toLowerCase();
    if (!query) return allDocumentRows;
    return allDocumentRows.filter((document) => [document.title, document.portable_relative_uri]
      .some((value) => String(value ?? "").toLowerCase().includes(query)));
  }, [allDocumentRows, documentQuery]);
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/providers", {})),
  });
  const profile = objectValue(listValue(objectValue(providers.data).profiles)[0]);
  const profileModels = listValue(profile.models).map(String);
  const profileConfigured = Boolean(profile.configured);
  const modelIdValid = /^[A-Za-z0-9][A-Za-z0-9._:/+\-]{1,199}$/.test(model.trim()) && !model.includes("://");

  const extractionHistory = useQuery({
    queryKey: ["jobs", "local_extraction"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs", { params: { query: { kind: "local_extraction", limit: 50 } } })),
    refetchInterval: 3_000,
  });
  const extractionRows: Job[] = extractionHistory.data?.items ?? [];
  const searches = useQuery({
    queryKey: ["literature-searches"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/literature-searches", {})),
  });
  const searchRows = listValue(objectValue(searches.data).items).map(objectValue);
  const activeSearch = searchRows.find((item) => textValue(item.search_id) === activeSearchId) ?? searchRows[0];

  useEffect(() => {
    if (!activeSourceId && sourceRows[0]) setStage("folder", sourceRows[0].source_id, "");
  }, [activeSourceId, sourceRows.length]);
  useEffect(() => setSelectedDocumentIds([]), [activeSourceId, sourceDetail.data?.revision]);
  useEffect(() => {
    const canonical = sourceDetail.data?.canonical_source_id;
    if (canonical && canonical !== activeSourceId) setStage("papers", canonical, "");
  }, [sourceDetail.data?.canonical_source_id, activeSourceId]);
  useEffect(() => {
    if (!literatureOpen || !activeSourceId) return;
    setDestinationMode("existing");
    setDestinationSourceId(activeSourceId);
  }, [literatureOpen, activeSourceId]);
  useEffect(() => {
    if (!activeSearchId && activeSearch) {
      setActiveSearchId(textValue(activeSearch.search_id));
      setSelectedWorkIds(usableSelectedWorkIds(activeSearch));
    }
  }, [activeSearchId, activeSearch]);
  useEffect(() => {
    if (activeSearch && !acquisitionJobId) {
      setAcquisitionFolderName(localDataFolderName(textValue(activeSearch.query, textValue(activeSearch.goal))));
    }
  }, [activeSearch?.search_id]);
  const createManaged = useMutation({
    mutationFn: async (name: string) => dataOrThrow(await api.POST("/api/v1/local/sources/managed", { body: { name, goal: "", area: "", parent: null } })),
    onSuccess: (value) => {
      const payload = objectValue(value);
      const sourceId = textValue(payload.source_id);
      setCreatedLocation(textValue(payload.created_location));
      setManagedName("");
      setAcquisitionSourceId(sourceId);
      queryClient.invalidateQueries({ queryKey: ["local-sources"] });
      setStage("papers", sourceId, "");
    },
  });
  const connectFolder = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/local/sources", { body: { path: manualPath } })),
    onSuccess: (value) => {
      const sourceId = textValue(objectValue(value).source_id);
      setManualPath("");
      queryClient.invalidateQueries({ queryKey: ["local-sources"] });
      setStage("papers", sourceId, "");
    },
  });
  const chooseFolder = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/local/folder-picker", {})),
    onSuccess: (value) => {
      const sourceId = textValue(objectValue(value).source_id);
      queryClient.invalidateQueries({ queryKey: ["local-sources"] });
      setStage("papers", sourceId, "");
    },
  });
  const reveal = useMutation({
    mutationFn: async (sourceId: string) => dataOrThrow(await api.POST("/api/v1/local/sources/{source_id}/reveal", { params: { path: { source_id: sourceId } } })),
  });
  const revealStorage = useMutation({
    mutationFn: async (target: "working_directory" | "workspace" | "local_data" | "principles") => dataOrThrow(await api.POST("/api/v1/local/storage-layout/reveal", { body: { target } })),
  });
  const copyPath = async (sourceId: string) => {
    const path = textValue(locations.get(sourceId)?.absolute_path);
    if (!path) return;
    try {
      await copyText(path);
      setPathMessage("Full folder path copied.");
    } catch {
      setPathMessage("Clipboard access is unavailable. Select the visible path to copy it manually.");
    }
  };

  const indexSource = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/local/sources/{source_id}/indexes", { params: { path: { source_id: activeSourceId } } })),
    onSuccess: (value) => setIndexJobId(textValue(objectValue(value).job_id)),
  });
  const indexJob = useQuery({
    queryKey: ["job", indexJobId],
    enabled: Boolean(indexJobId),
    refetchInterval: (query) => terminalJobStates.has(String((query.state.data as Job | undefined)?.state ?? "")) ? false : 750,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: indexJobId } } })) as Job,
  });
  useEffect(() => {
    if (indexJob.data?.state === "succeeded") {
      queryClient.invalidateQueries({ queryKey: ["local-source", activeSourceId] });
      queryClient.invalidateQueries({ queryKey: ["source-documents", activeSourceId] });
      queryClient.invalidateQueries({ queryKey: ["local-sources"] });
    }
  }, [indexJob.data?.state]);
  useEffect(() => {
    if (
      stage === "papers"
      && activeSourceId
      && sourceDetail.data?.status === "ready"
      && sourceDetail.data.document_count === 0
      && !automaticallyIndexed.current.has(activeSourceId)
      && !indexSource.isPending
    ) {
      automaticallyIndexed.current.add(activeSourceId);
      indexSource.mutate();
    }
  }, [stage, activeSourceId, sourceDetail.data?.status, sourceDetail.data?.document_count]);

  const saveCredential = useMutation({
    mutationFn: async () => dataOrThrow(await api.PUT("/api/v1/provider-profiles/{provider_id}/credential", { params: { path: { provider_id: "siliconflow" } }, body: { api_key: credential } })),
    onSuccess: () => {
      setCredential("");
      setCredentialMessage("Credential saved privately in this workspace. No network call was made.");
      queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });
  const testCredential = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/provider-profiles/{provider_id}/test", { params: { path: { provider_id: "siliconflow" } } })),
    onSuccess: (value) => {
      const result = objectValue(value);
      const category = textValue(result.category, "provider_unavailable");
      if (Boolean(result.ok)) {
        setCredentialMessage(`Connection succeeded through ${textValue(result.base_url, "an authorized SiliconFlow endpoint")}.`);
      } else if (category === "rate_limited") {
        setCredentialMessage("The credential was accepted, but SiliconFlow is rate-limiting requests. Wait briefly, then retry the failed papers.");
      } else if (category === "authentication") {
        setCredentialMessage("SiliconFlow rejected the credential at both authorized regional endpoints. Save a different key, then test again.");
      } else if (category === "timeout") {
        setCredentialMessage("The connection test timed out. The saved credential was not changed; try again when the provider is reachable.");
      } else {
        setCredentialMessage("SiliconFlow could not be reached. The saved credential was not changed; try again later.");
      }
      queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });
  const deleteCredential = useMutation({
    mutationFn: async () => dataOrThrow(await api.DELETE("/api/v1/provider-profiles/{provider_id}/credential", { params: { path: { provider_id: "siliconflow" } } })),
    onSuccess: () => {
      setCredentialMessage("Workspace credential removed. Principia will use an environment credential if configured.");
      queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  const startExtraction = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/local/extractions", { body: {
      source_id: activeSourceId,
      source_revision: sourceDetail.data?.revision ?? 1,
      document_ids: selectedDocumentIds,
      selection_mode: "exact",
      context: { research_goal_id: null, research_focus: researchFocus.trim() || null },
      goal_id: "",
      goal: "",
      area: "",
      provider_profile_id: "siliconflow",
      model: model.trim(),
      policy,
      egress_confirmed: policy === "remote" ? confirmEgress : false,
      quality_policy: "scientific-principle-v2",
      limits: { max_http_attempts: 140, max_input_tokens: 1_500_000, max_output_tokens: 300_000, max_pro_calls: 20, max_wall_seconds: 10_800, max_repairs_per_unit: 1, concurrency: 3, reasoning_tokens_per_request: 512 },
    } })),
    onSuccess: (value) => {
      const jobId = textValue(objectValue(value).job_id);
      setActiveJobId(jobId);
      // The immutable selection is persisted with the job. Clear the working
      // checklist so returning to the paper inventory cannot silently combine
      // an old selection with papers chosen for a later run.
      setSelectedDocumentIds([]);
      queryClient.invalidateQueries({ queryKey: ["jobs", "local_extraction"] });
      setStage("results", activeSourceId, jobId);
    },
  });
  const extractionJob = useQuery({
    queryKey: ["job", activeJobId],
    enabled: Boolean(activeJobId),
    refetchInterval: (query) => terminalJobStates.has(String((query.state.data as Job | undefined)?.state ?? "")) ? false : 750,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: activeJobId } } })) as Job,
  });
  const jobUnits = useQuery({
    queryKey: ["job-units", activeJobId],
    enabled: Boolean(activeJobId),
    refetchInterval: extractionJob.data && !terminalJobStates.has(extractionJob.data.state) ? 1_500 : false,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs/{job_id}/units", { params: { path: { job_id: activeJobId } } })),
  });
  const unitRows = listValue(objectValue(jobUnits.data).items).map(objectValue);
  const failedUnits = unitRows.filter((item) => textValue(item.state) === "failed");
  const controlJob = async (action: "pause" | "resume" | "cancel" | "retry-failed") => {
    if (!activeJobId) return;
    const path = { job_id: activeJobId };
    if (action === "pause") await dataOrThrow(await api.POST("/api/v1/jobs/{job_id}/pause", { params: { path } }));
    if (action === "resume") await dataOrThrow(await api.POST("/api/v1/jobs/{job_id}/resume", { params: { path } }));
    if (action === "cancel") await dataOrThrow(await api.POST("/api/v1/jobs/{job_id}/cancel", { params: { path } }));
    if (action === "retry-failed") {
      const value = dataOrThrow(await api.POST("/api/v1/jobs/{job_id}/retry-failed", { params: { path } }));
      const newJobId = textValue(objectValue(value).job_id);
      setActiveJobId(newJobId);
      setStage("results", activeSourceId, newJobId);
    }
    extractionJob.refetch();
  };

  const candidates = useQuery({
    queryKey: ["local-candidates", activeSourceId, resultView, activeJobId],
    enabled: Boolean(activeSourceId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/candidates", { params: { query: { q: "", area: "", assessment: "", eligibility: resultView, discovery_id: activeJobId, dataset_id: "", goal_id: "", source_id: activeSourceId, quality_state: resultView, limit: 100, cursor: "" } } })),
    refetchInterval: extractionJob.data && !terminalJobStates.has(extractionJob.data.state) ? 1_500 : false,
  });
  const candidatePayload = objectValue(candidates.data);
  const candidateRows = listValue(candidatePayload.items).map(objectValue);
  useEffect(() => {
    if (!candidateRows.some((item) => textValue(item.candidate_id) === selectedCandidateId)) setSelectedCandidateId(textValue(candidateRows[0]?.candidate_id));
  }, [candidateRows, selectedCandidateId]);
  const candidateDetail = useQuery({
    queryKey: ["local-candidate", selectedCandidateId],
    enabled: Boolean(selectedCandidateId),
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/candidates/{candidate_id}", { params: { path: { candidate_id: selectedCandidateId } } })),
  });
  const detail = objectValue(candidateDetail.data);
  const detailMeta = objectValue(detail.local_metadata);
  const argument = objectValue(detail.scientific_argument);
  const evidence = listValue(detail.evidence).map(objectValue);
  const areaSuggestions = listValue(detail.area_suggestions).map(objectValue);
  const updateArea = useMutation({
    mutationFn: async ({ action, area }: { action: "accept" | "reject" | "create"; area: string }) => {
      if (action === "create") return dataOrThrow(await api.POST("/api/v1/local/candidates/{candidate_id}/area-suggestions", { params: { path: { candidate_id: selectedCandidateId } }, body: { area, rationale: "Added during human review" } }));
      if (action === "accept") return dataOrThrow(await api.POST("/api/v1/local/candidates/{candidate_id}/area-suggestions/{area}/accept", { params: { path: { candidate_id: selectedCandidateId, area } } }));
      return dataOrThrow(await api.POST("/api/v1/local/candidates/{candidate_id}/area-suggestions/{area}/reject", { params: { path: { candidate_id: selectedCandidateId, area } } }));
    },
    onSuccess: () => { setNewArea(""); queryClient.invalidateQueries({ queryKey: ["local-candidate", selectedCandidateId] }); },
  });

  const createSearch = useMutation({
    mutationFn: async () => dataOrThrow(await api.POST("/api/v1/local/literature-searches", { body: { query: searchQuestion, goal: "", area: "", target_count: targetCount, semantic_ranking: semanticRanking, source_id: destinationMode === "existing" ? destinationSourceId : "" } })),
    onSuccess: (value) => {
      const job = objectValue(value);
      const result = objectValue(job.result);
      setSearchJobId(textValue(job.job_id));
      setPendingSearchId(textValue(result.search_id));
      // A new asynchronous search must never inherit the previous preview's
      // paper selection while its own provisional results are still empty.
      setSelectedWorkIds([]);
      setAcquisitionFolderName(localDataFolderName(searchQuestion));
    },
  });
  const searchJob = useQuery({
    queryKey: ["job", searchJobId],
    enabled: Boolean(searchJobId),
    refetchInterval: (query) => terminalJobStates.has(String((query.state.data as Job | undefined)?.state ?? "")) ? false : 750,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: searchJobId } } })) as Job,
  });
  const pendingSearch = useQuery({
    queryKey: ["literature-search", pendingSearchId],
    enabled: Boolean(pendingSearchId),
    // The job can reach its terminal state a fraction before the finalized
    // search revision is observable. Keep polling the search itself until its
    // immutable default selection is present; otherwise the preview can show
    // "0 selected" even though the backend selected the requested papers.
    refetchInterval: (query) => Boolean(objectValue(query.state.data).selection_finalized) ? false : 1_000,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/local/literature-searches/{search_id}", { params: { path: { search_id: pendingSearchId } } })),
  });
  useEffect(() => {
    if (pendingSearchId && Boolean(objectValue(pendingSearch.data).selection_finalized)) {
      const latest = objectValue(pendingSearch.data);
      setSelectedWorkIds(defaultNewWorkIds(latest, destinationWorkIds));
      queryClient.invalidateQueries({ queryKey: ["literature-searches"] });
    }
  }, [pendingSearchId, pendingSearch.data, destinationWorkIds]);
  useEffect(() => {
    if (pendingSearchId && searchRows.some((item) => textValue(item.search_id) === pendingSearchId) && Boolean(objectValue(pendingSearch.data).selection_finalized)) {
      setActiveSearchId(pendingSearchId);
      setPendingSearchId("");
    }
  }, [searchRows, pendingSearchId, pendingSearch.data]);
  const provisionalRows = listValue(objectValue(searchJob.data?.result).provisional_results).map(objectValue);
  const pendingRows = listValue(objectValue(pendingSearch.data).results).map(objectValue);
  const activeRows = listValue(activeSearch?.results).map(objectValue);
  const showingPendingSearch = Boolean(pendingSearchId && pendingSearchId !== textValue(activeSearch?.search_id));
  const previewRows = showingPendingSearch ? (pendingRows.length ? pendingRows : provisionalRows) : activeRows;
  const displaySearch = showingPendingSearch ? objectValue(pendingSearch.data) : objectValue(activeSearch);
  const usablePreviewIds = previewRows.filter(searchWorkUsable).map(searchWorkId);
  const newUsablePreviewIds = usablePreviewIds.filter((workId) => !destinationWorkIds.has(workId));
  const alreadySavedCount = usablePreviewIds.length - newUsablePreviewIds.length;
  const allUsableSelected = Boolean(newUsablePreviewIds.length) && newUsablePreviewIds.every((workId) => selectedWorkIds.includes(workId));

  const acquire = useMutation({
    mutationFn: async () => {
      const searchId = textValue(activeSearch?.search_id);
      await dataOrThrow(await api.PATCH("/api/v1/local/literature-searches/{search_id}/selection", { params: { path: { search_id: searchId } }, body: { work_ids: selectedWorkIds } }));
      const destination = destinationMode === "existing"
        ? { source_id: destinationSourceId, work_ids: selectedWorkIds }
        : { folder_name: acquisitionFolderName.trim(), work_ids: selectedWorkIds };
      return dataOrThrow(await api.POST("/api/v1/local/literature-searches/{search_id}/acquisitions", { params: { path: { search_id: searchId } }, body: destination }));
    },
    onSuccess: (value) => {
      const job = objectValue(value);
      const sourceId = textValue(objectValue(job.checkpoint).source_id);
      setAcquisitionSourceId(sourceId);
      setAcquisitionJobId(textValue(job.job_id));
      queryClient.invalidateQueries({ queryKey: ["local-sources"] });
    },
  });
  const acquisitionJob = useQuery({
    queryKey: ["job", acquisitionJobId],
    enabled: Boolean(acquisitionJobId),
    refetchInterval: (query) => terminalJobStates.has(String((query.state.data as Job | undefined)?.state ?? "")) ? false : 750,
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: acquisitionJobId } } })) as Job,
  });
  useEffect(() => {
    if (acquisitionJob.data?.state === "succeeded") {
      setAcquisitionReceipt(objectValue(acquisitionJob.data.result));
      queryClient.invalidateQueries({ queryKey: ["local-sources"] });
      queryClient.invalidateQueries({ queryKey: ["local-source", acquisitionSourceId] });
      queryClient.invalidateQueries({ queryKey: ["source-documents", acquisitionSourceId] });
      setLiteratureOpen(false);
      setStage("papers", acquisitionSourceId, "");
    }
  }, [acquisitionJob.data?.state]);

  const activeMetrics = objectValue(extractionJob.data?.result);
  const allVisibleSelected = documentRows.length > 0 && documentRows.filter((item) => item.extraction_eligible).every((item) => selectedDocumentIds.includes(item.document_id));
  const allExtractableDocumentIds = allDocumentRows.filter((item) => item.extraction_eligible).map((item) => item.document_id);
  const unextractedDocumentIds = allDocumentRows.filter((item) => item.extraction_eligible && item.extraction_status === "not_started").map((item) => item.document_id);
  const currentLocation = locations.get(activeSourceId);
  const destinationSource = sourceRows.find((source) => source.source_id === destinationSourceId);
  const destinationLocation = locations.get(destinationSourceId);
  const activeError = createManaged.error ?? connectFolder.error ?? chooseFolder.error ?? reveal.error ?? indexSource.error ?? saveCredential.error ?? testCredential.error ?? deleteCredential.error ?? startExtraction.error ?? createSearch.error ?? acquire.error;
  const controlSearch = async (action: "pause" | "cancel" | "retry-failed") => {
    if (!searchJobId) return;
    const path = { job_id: searchJobId };
    if (action === "pause") await dataOrThrow(await api.POST("/api/v1/jobs/{job_id}/pause", { params: { path } }));
    if (action === "cancel") await dataOrThrow(await api.POST("/api/v1/jobs/{job_id}/cancel", { params: { path } }));
    if (action === "retry-failed") {
      const value = dataOrThrow(await api.POST("/api/v1/jobs/{job_id}/retry-failed", { params: { path } }));
      const replacement = objectValue(value);
      setSearchJobId(textValue(replacement.job_id));
      setPendingSearchId(textValue(objectValue(replacement.result).search_id));
    }
    searchJob.refetch();
  };

  return <div className="page local-page">
    <PageHeader eyebrow="Private evidence, under your control" title="Local Discovery" description="Choose a real private folder, select its papers, then extract reusable scientific findings from exactly that selection." actions={<button onClick={() => openLiteratureForFolder()}>{activeSourceId ? "Add papers to this folder" : "Find public literature"}</button>} />
    <div className="privacy-banner"><span aria-hidden="true">⌂</span><div><strong>Raw sources and derived Principles stay separate</strong><p>Managed papers live under the working directory’s <code>local_data/</code>; external folders stay where you put them. Derived Principles live under <code>workspace/</code> and remain browsable if the raw folder is removed. Remote evidence leaves the computer only after your explicit per-run confirmation.</p></div></div>
    {storageLayout.data ? <section className="storage-layout-card" aria-label="Working directory layout">
      <div className="storage-layout-heading"><div><span className="step-label">Active working directory</span><h2>{storageLayout.data.working_directory}</h2><p>Principia created both folders when this working directory was opened.</p></div><div><button onClick={() => copyText(storageLayout.data.working_directory).then(() => setPathMessage("Working-directory path copied."))}>Copy path</button><button onClick={() => revealStorage.mutate("working_directory")}>Open</button></div></div>
      <div className="storage-boundaries"><article><span className="folder-glyph">▱</span><div><strong>local_data</strong><code>{storageLayout.data.local_data}</code><small>Raw PDFs, full text, abstracts, and any managed literature folders. This directory is detachable.</small></div><button onClick={() => revealStorage.mutate("local_data")}>Open</button></article><article><span className="folder-glyph">▰</span><div><strong>workspace</strong><code>{storageLayout.data.workspace}</code><small>Durable Principles, evidence references, jobs, indexes, and application state.</small></div><button onClick={() => revealStorage.mutate("workspace")}>Open</button></article></div>
    </section> : storageLayout.isLoading ? <LoadingState label="Opening the working-directory layout…" /> : null}
    <nav className="local-stage-nav" aria-label="Local Discovery stages">{stages.map((item, index) => <button key={item.id} className={stage === item.id ? "active" : ""} onClick={() => setStage(item.id)}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.label}</strong><small>{item.helper}</small></button>)}</nav>
    {activeError ? <ErrorState error={activeError} /> : null}
    {pathMessage ? <p className="path-copy-message" role="status">{pathMessage}</p> : null}

    {stage === "folder" ? <section className="folder-first-panel">
      <div className="stage-heading"><span className="step-label">01 · Local source</span><h2>Choose a source folder inside this working directory</h2><p>These cards are literature sources, not working directories. Change the entire isolated project from the working-directory selector in Principles Library. Every source shows its complete path below.</p></div>
      {createdLocation ? <div className="created-location"><div><strong>Managed folder created</strong><span>{createdLocation}</span><small>This exact location remains available on its folder card.</small></div><button onClick={async () => { try { await copyText(createdLocation); setPathMessage("Full folder path copied."); } catch { setPathMessage("Clipboard access is unavailable. Select the visible path to copy it manually."); } }}>Copy Path</button></div> : null}
      <div className="folder-choice-grid"><article><h3>Registered private folders</h3>{sources.isLoading || pathDisclosures.isLoading ? <LoadingState label="Resolving private folder locations…" /> : null}{sources.isError || pathDisclosures.isError ? <ErrorState error={sources.error ?? pathDisclosures.error} retry={() => { sources.refetch(); pathDisclosures.refetch(); }} /> : null}<div className="source-card-list">{sourceRows.map((source) => { const location = locations.get(source.source_id); const path = textValue(location?.absolute_path, "Path unavailable"); return <article className={`source-location-card ${activeSourceId === source.source_id ? "selected" : ""}`} key={source.source_id}><button className="source-select" onClick={() => setStage("papers", source.source_id, "")}><span className="folder-glyph">▱</span><span><strong>{source.display_name}</strong><code>{path}</code><small>{source.document_count} documents · {source.pdf_count} PDFs · {source.text_full_text_count} full-text files · {source.abstract_only_count} abstract only · revision {source.revision}</small></span><span className={`availability ${Boolean(location?.available) ? "ready" : "missing"}`}>{Boolean(location?.available) ? "Available" : "Unavailable"}</span></button><div><button onClick={() => copyPath(source.source_id)} disabled={!textValue(location?.absolute_path)}>Copy Path</button><button onClick={() => reveal.mutate(source.source_id)} disabled={!Boolean(location?.available)}>Open Folder</button></div></article>; })}</div>{!sourceRows.length && !sources.isLoading ? <EmptyState title="No private folders yet"><p>Connect an existing folder or create a managed one.</p></EmptyState> : null}<button className="literature-assistant-link" onClick={() => setLiteratureOpen(true)}><strong>Need papers?</strong><span>Search public literature and acquire permitted files into a real folder first.</span><em>Open literature helper →</em></button></article>
        <article><h3>Add a private folder</h3>{Boolean(objectValue(picker.data).available) ? <button className="picker-button" onClick={() => chooseFolder.mutate()}>Choose folder on this computer…</button> : null}<label><span>Existing absolute path</span><div className="input-action"><input value={manualPath} onChange={(event) => setManualPath(event.target.value)} placeholder="/absolute/path/to/papers" /><button onClick={() => connectFolder.mutate()} disabled={!manualPath.trim()}>Connect</button></div></label><p>Or create a named raw-source folder under <code>local_data/</code>. No Principle records are written there.</p><label><span>Local data folder name</span><input value={managedName} onChange={(event) => setManagedName(event.target.value)} placeholder="e.g. test-ASD" /></label><button className="primary full" onClick={() => createManaged.mutate(managedName)} disabled={!managedName.trim()}>Create local data folder</button></article></div>
    </section> : null}

    {stage === "papers" ? <section className="paper-selection-panel">
      <div className="stage-heading split"><div><span className="step-label">02 · Paper inventory</span><h2>{sourceDetail.data?.display_name ?? "Private folder"}</h2><code className="stage-path">{textValue(currentLocation?.absolute_path, sourceDetail.data?.display_location)}</code></div><div className="stage-actions"><button onClick={() => copyPath(activeSourceId)}>Copy Path</button><button onClick={() => reveal.mutate(activeSourceId)}>Open Folder</button><button onClick={() => openLiteratureForFolder(activeSourceId)}>Find papers for this folder</button><button onClick={() => indexSource.mutate()} disabled={indexSource.isPending}>{indexSource.isPending ? "Starting…" : "Refresh index"}</button><button className="primary" onClick={() => setStage("extract")} disabled={!selectedDocumentIds.length}>Continue with {selectedDocumentIds.length}</button></div></div>
      {indexJob.data && !terminalJobStates.has(indexJob.data.state) ? <div className="inline-job"><JobProgress job={indexJob.data} /></div> : null}
      {indexJob.data?.state === "failed" ? <ErrorState error={indexJob.data.error} retry={() => indexSource.mutate()} /> : null}
      {acquisitionReceipt && textValue(acquisitionReceipt.source_id) === activeSourceId ? <div className="acquisition-receipt" role="status"><div><strong>{numberValue(acquisitionReceipt.acquired_count)} usable documents saved</strong><p>{numberValue(acquisitionReceipt.pdf_count)} PDFs + {numberValue(acquisitionReceipt.text_full_text_count)} plain-text full texts + {numberValue(acquisitionReceipt.abstract_only_count)} permitted abstract-only records. Every document is self-contained under <code>papers/</code> in <strong>{textValue(currentLocation?.absolute_path, sourceDetail.data?.display_location)}</strong>. Acquisition did not start extraction.</p></div><div><button onClick={() => copyPath(activeSourceId)}>Copy Path</button><button onClick={() => reveal.mutate(activeSourceId)}>Open Folder</button><button onClick={() => setAcquisitionReceipt(null)}>Dismiss</button></div></div> : null}
      <div className="paper-inventory-toolbar"><input aria-label="Filter papers" value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} placeholder="Filter title or filename…" /><button onClick={() => setSelectedDocumentIds(allExtractableDocumentIds)}>Select all papers ({allExtractableDocumentIds.length})</button><button onClick={() => setSelectedDocumentIds(unextractedDocumentIds)} disabled={!unextractedDocumentIds.length}>Select not yet extracted ({unextractedDocumentIds.length})</button>{documentQuery ? <button onClick={() => setSelectedDocumentIds(allVisibleSelected ? selectedDocumentIds.filter((id) => !documentRows.some((doc) => doc.document_id === id)) : Array.from(new Set([...selectedDocumentIds, ...documentRows.filter((doc) => doc.extraction_eligible).map((doc) => doc.document_id)])))}>{allVisibleSelected ? "Clear filtered" : "Select filtered"}</button> : null}<button onClick={() => setSelectedDocumentIds([])} disabled={!selectedDocumentIds.length}>Clear</button><span>{selectedDocumentIds.length} selected · {sourceDetail.data?.extractable_count ?? 0} extractable</span></div>
      {documents.isLoading ? <LoadingState label="Reading indexed papers…" /> : null}{documents.isError ? <ErrorState error={documents.error} retry={() => documents.refetch()} /> : null}
      {!documents.isLoading && !documentRows.length ? <EmptyState title="No indexed papers"><p>Add PDFs or text files to the folder, refresh the index, or search public literature and add the results directly to this folder.</p><button onClick={() => openLiteratureForFolder(activeSourceId)}>Find papers for this folder</button></EmptyState> : <div className="document-table"><div className="document-header"><span /><span>Paper</span><span>Content</span><span>Size</span><span>Extraction</span><span>Principles</span></div>{documentRows.map((document) => { const contentLabel = document.content_representation === "pdf" ? "PDF full text" : document.content_representation === "full_text" ? "Plain-text full text" : document.content_representation === "abstract" ? "Abstract only" : "Local document"; const extractionLabel = document.extraction_status === "processed" ? "Processed" : document.extraction_status === "processing" ? "In progress" : document.extraction_status === "failed" ? "Needs retry" : "Not extracted"; return <label className={!document.extraction_eligible ? "disabled" : ""} key={document.document_id}><input type="checkbox" checked={selectedDocumentIds.includes(document.document_id)} disabled={!document.extraction_eligible} onChange={() => setSelectedDocumentIds((current) => current.includes(document.document_id) ? current.filter((id) => id !== document.document_id) : [...current, document.document_id])} /><span><strong>{document.title}</strong><small>{document.year ?? "Year unknown"} · {document.portable_relative_uri}</small></span><span className={`document-status ${document.content_representation}`}>{contentLabel}</span><span className="document-size">{fileSizeLabel(document.content_byte_size)}</span><span>{extractionLabel}</span><span>{document.principle_count}</span></label>; })}</div>}
    </section> : null}

    {stage === "extract" ? <section className="extraction-config-panel">
      <div className="stage-heading"><span className="step-label">03 · Evidence-grounded extraction</span><h2>Extract from exactly {selectedDocumentIds.length} selected paper{selectedDocumentIds.length === 1 ? "" : "s"}</h2><p>Principia identifies source findings, converts only transferable scientific relationships, verifies every claim part against exact text, and holds uncertain drafts back.</p></div>
      <div className="extraction-config-grid"><div><label><span>Research focus <em>optional</em></span><textarea value={researchFocus} onChange={(event) => setResearchFocus(event.target.value)} placeholder="Leave blank to extract broadly across the selected papers." /></label><p className="field-note">A focus prioritizes relevant passages and creates a research-question collection. It never changes whether a finding passes evidence checks.</p><div className="selection-receipt"><strong>{paperLabel(selectedDocumentIds.length)} selected</strong><span>No Area is required. Area labels are suggested only after extraction and remain editable.</span></div></div>
        <div><label><span>Model policy</span><SmartSelect ariaLabel="Model policy" value={policy} onChange={(value) => setPolicy(value as "remote" | "no_llm")} options={[{ value: "remote", label: "Remote · SiliconFlow", description: "Send bounded excerpts only after confirmation" }, { value: "no_llm", label: "No LLM · index only", description: "No generated Principle drafts" }]} /></label><label className="model-id-field"><span>Model ID</span><input aria-label="Extraction model ID" value={model} onChange={(event) => setModel(event.target.value)} disabled={policy === "no_llm"} spellCheck={false} placeholder="provider/model-name" /><small>Enter any model ID supported by SiliconFlow. Principia never switches it silently.</small></label><div className="model-suggestions" aria-label="Suggested extraction models">{profileModels.map((item) => <button type="button" className={model === item ? "selected" : ""} onClick={() => setModel(item)} disabled={policy === "no_llm"} key={item}>{item.split("/").at(-1)}</button>)}</div>{policy === "remote" && !modelIdValid ? <p className="field-error" role="alert">Enter an exact model ID, for example <code>organization/model-name</code>.</p> : null}<div className="provider-credential-card"><div><strong>SiliconFlow credential</strong><span>{profileConfigured ? `Configured · ${textValue(profile.credential_source, "private source")}` : "Not configured"}</span><small>{textValue(profile.base_url, "Authorized provider origin is fixed by Principia")}</small></div><label><span>New API key</span><input type="password" autoComplete="off" value={credential} onChange={(event) => setCredential(event.target.value)} placeholder="Paste a key to save privately" /></label><div><button onClick={() => saveCredential.mutate()} disabled={credential.length < 8 || saveCredential.isPending}>{saveCredential.isPending ? "Saving…" : "Save"}</button><button onClick={() => testCredential.mutate()} disabled={!profileConfigured || testCredential.isPending}>{testCredential.isPending ? "Testing…" : "Test connection"}</button><button onClick={() => deleteCredential.mutate()} disabled={!profileConfigured || deleteCredential.isPending}>Delete</button></div>{credentialMessage ? <p role="status">{credentialMessage}</p> : null}</div>{policy === "remote" ? <label className="checkbox"><input type="checkbox" checked={confirmEgress} onChange={(event) => setConfirmEgress(event.target.checked)} /><span>I confirm that bounded excerpts from {selectedDocumentIds.length === 1 ? "this paper" : `these ${selectedDocumentIds.length} papers`} may be sent to SiliconFlow for this run.</span></label> : null}</div>
        <aside><h3>Evidence safeguards</h3><ul><li>Paper summaries, contribution claims, and novelty claims are excluded.</li><li>Every claim part must map to exact source text.</li><li>Causal, comparative, numeric, and scope language must be supported.</li><li>One-paper findings stay limited to the reported conditions.</li><li>A second-pass evidence check must agree; otherwise the draft is held back.</li></ul><details><summary>Advanced run limits</summary><p>140 HTTP attempts · 1.5M input tokens · 300k output tokens · up to 3 papers processed concurrently · one repair per paper · three-hour wall limit. Completed papers appear immediately and remain saved while the run continues.</p></details><button className="primary full" onClick={() => startExtraction.mutate()} disabled={!selectedDocumentIds.length || startExtraction.isPending || (policy === "remote" && (!confirmEgress || !profileConfigured || !modelIdValid))}>{startExtraction.isPending ? "Starting durable extraction…" : `Extract from ${paperLabel(selectedDocumentIds.length)}`}</button></aside></div>
    </section> : null}

    {stage === "results" ? <section className="extraction-results-panel">
      <div className="stage-heading split"><div><span className="step-label">04 · Review results</span><h2>Reusable Principle drafts</h2><p>Passing evidence checks means ready for human review—not proven true or globally published.</p></div><div className="stage-actions"><SmartSelect ariaLabel="Extraction history" value={activeJobId} onChange={(value) => { setActiveJobId(value); setStage("results", activeSourceId, value); }} options={extractionRows.map((job) => ({ value: job.job_id, label: job.stage, description: `${job.state} · ${job.job_id.slice(-8)}` }))} placeholder="Choose an extraction run…" /><button className="primary" onClick={() => navigate(`/map?scope=local&source=${encodeURIComponent(activeSourceId)}`)}>Open in Explorer</button></div></div>
      {extractionJob.data ? <div className="extraction-job"><JobProgress job={extractionJob.data} /><div className="job-controls">{extractionJob.data.state === "running" ? <button onClick={() => controlJob("pause")}>Pause</button> : null}{extractionJob.data.stage.toLowerCase().includes("paused") ? <button onClick={() => controlJob("resume")}>Resume</button> : null}{!terminalJobStates.has(extractionJob.data.state) ? <button onClick={() => controlJob("cancel")}>Cancel</button> : null}{["failed", "interrupted", "cancelled"].includes(extractionJob.data.state) || failedUnits.length ? <button onClick={() => controlJob("retry-failed")}>Retry failed papers</button> : null}</div><div className="metric-strip">{[["Selected", activeMetrics.selected_documents], ["Processed", activeMetrics.processed_documents], ["Source findings", activeMetrics.raw_atoms], ["Reusable findings", activeMetrics.raw_arguments], ["Ready", activeMetrics.eligible_candidates], ["Already present", activeMetrics.duplicate_candidates], ["Held back", activeMetrics.quarantined_candidates], ["Failed", activeMetrics.failed_documents]].map(([label, value]) => <div key={String(label)}><strong>{String(value ?? 0)}</strong><span>{String(label)}</span></div>)}</div>{extractionJob.data.error ? <ErrorState error={extractionJob.data.error} retry={() => controlJob("retry-failed")} /> : null}</div> : <EmptyState title="No extraction run selected"><p>Select papers and start an extraction first.</p></EmptyState>}
      {failedUnits.length ? <details className="failed-unit-list"><summary>{failedUnits.length} paper{failedUnits.length === 1 ? "" : "s"} need attention</summary><ul>{failedUnits.map((unit) => <li key={textValue(unit.unit_id)}><strong>{textValue(unit.work_title)}</strong><span>{textValue(objectValue(unit.error).message, "Extraction failed")}</span></li>)}</ul></details> : null}
      <div className="candidate-workspace"><div className="candidate-table"><div className="section-heading"><div><span className="step-label">This run</span><h2>{numberValue(candidatePayload.total)} {resultView === "eligible" ? "ready to review" : "held back"}</h2></div><div className="segmented"><button className={resultView === "eligible" ? "selected" : ""} onClick={() => setResultView("eligible")}>Ready to review</button><button className={resultView === "quarantined" ? "selected" : ""} onClick={() => setResultView("quarantined")}>Held back</button></div></div>{candidates.isLoading ? <LoadingState label="Loading Principle drafts…" /> : null}{candidates.isError ? <ErrorState error={candidates.error} retry={() => candidates.refetch()} /> : null}<div className="candidate-rows">{candidateRows.map((candidate) => { const id = textValue(candidate.candidate_id); const oneSource = textValue(candidate.generalization_level) !== "cross_study"; return <button key={id} className={selectedCandidateId === id ? "selected" : ""} onClick={() => setSelectedCandidateId(id)}><span className="source-mark local" /><span><strong>{textValue(candidate.title)}</strong><small>{textValue(candidate.area) === "uncategorized" ? "Not categorized" : textValue(candidate.area).replaceAll("-", " ")} · {numberValue(candidate.source_count)} paper{numberValue(candidate.source_count) === 1 ? "" : "s"} · {oneSource ? "Limited to reported conditions" : "Supported by multiple papers"}</small><p>{textValue(candidate.claim)}</p>{textValue(candidate.quarantine_reason) ? <em>{reasons(textValue(candidate.quarantine_reason))[0]}</em> : null}</span></button>; })}</div></div>
        <aside className="candidate-inspector">{candidateDetail.isLoading ? <LoadingState label="Opening evidence…" /> : null}{detail.title ? <><span className="eyebrow">Local Principle · Human review pending</span><h2>{textValue(detail.title)}</h2><p className="claim">{textValue(detail.claim)}</p><div className="quality-badges"><span>{resultView === "eligible" ? "Evidence checks passed" : "Held back"}</span><span>{textValue(argument.generalization_level) === "cross_study" ? "Supported by multiple papers" : "Limited to reported conditions"}</span><span>{evidence.length} exact anchor{evidence.length === 1 ? "" : "s"}</span></div>{textValue(detailMeta.quarantine_reason) ? <div className="quarantine-reasons"><strong>Why this draft was held back</strong><ul>{reasons(textValue(detailMeta.quarantine_reason)).map((reason) => <li key={reason}>{reason}</li>)}</ul></div> : null}<h3>Applicability</h3><p>{listValue(argument.conditions).map(String).join("; ") || "See source conditions."}</p><h3>Boundary</h3><p>{listValue(argument.boundary).map(String).join("; ") || "Requires human review."}</p><h3>How it can be tested</h3><p>{textValue(argument.testability, textValue(detail.falsifier))}</p><h3>Area labels <small>organization only</small></h3><div className="area-suggestions">{areaSuggestions.filter((item) => textValue(item.state) !== "rejected").map((item) => <span key={textValue(item.area)}>{textValue(item.area).replaceAll("-", " ")} · {textValue(item.state)}<button onClick={() => updateArea.mutate({ action: textValue(item.state) === "confirmed" ? "reject" : "accept", area: textValue(item.area) })}>{textValue(item.state) === "confirmed" ? "Remove" : "Accept"}</button></span>)}<div><input value={newArea} onChange={(event) => setNewArea(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))} placeholder="new-area-label" /><button onClick={() => updateArea.mutate({ action: "create", area: newArea })} disabled={!newArea}>Add</button></div></div><div className="candidate-actions"><button className="primary" onClick={() => navigate(`/map?scope=local&source=${encodeURIComponent(activeSourceId)}&selected=${encodeURIComponent(selectedCandidateId)}`)}>Open in Explorer</button><button onClick={() => downloadJson(`principia-${selectedCandidateId}`, candidateDetail.data)}>Export</button></div><div className="evidence-cards"><h3>Exact paper evidence</h3>{evidence.map((item) => <article key={textValue(item.evidence_id)}><strong>{textValue(item.work_title)}</strong><small>{textValue(item.section)}{item.page_start ? ` · page ${String(item.page_start)}` : ""}</small><blockquote>{textValue(item.quotation)}</blockquote></article>)}</div><details className="technical-record"><summary>Technical record</summary><pre>{JSON.stringify({ metadata: detailMeta, evaluations: detail.quality_evaluations }, null, 2)}</pre></details></> : <EmptyState title="Select a Principle draft"><p>Inspect its reusable claim, conditions, evidence, and Area suggestions.</p></EmptyState>}</aside></div>
    </section> : null}

    {literatureOpen ? <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setLiteratureOpen(false); }}><aside className="literature-drawer" role="dialog" aria-modal="true" aria-labelledby="literature-title"><header><div><span className="eyebrow">Optional folder-building assistant</span><h2 id="literature-title">Find public literature</h2><p>Search metadata first, review the papers, then acquire permitted content into a visible folder. Extraction never starts automatically.</p></div><button aria-label="Close literature helper" onClick={() => setLiteratureOpen(false)}>×</button></header>
      <section><span className="step-label">A · Search metadata only</span>{destinationMode === "existing" && destinationSource ? <div className="acquisition-contract" role="status"><strong>Adding papers to {destinationSource.display_name}</strong><span>After you review the results, acquired papers will be saved to <code>{textValue(destinationLocation?.absolute_path, destinationSource.display_location)}</code>. Existing files and Principles are preserved.</span></div> : null}<label><span>Research question</span><textarea value={searchQuestion} onChange={(event) => setSearchQuestion(event.target.value)} placeholder="Which scientific mechanism, relationship, or boundary are you investigating?" /></label><label><span>Target papers</span><input type="number" min={1} max={50} value={targetCount} onChange={(event) => setTargetCount(Number(event.target.value))} /></label><label className="checkbox"><input type="checkbox" checked={semanticRanking} onChange={(event) => setSemanticRanking(event.target.checked)} /><span>Use semantic ranking when a workspace SiliconFlow credential is available. This sends only the research question and public paper metadata; without a credential, Principia falls back to deterministic scholarly ranking.</span></label><button className="primary full" onClick={() => createSearch.mutate()} disabled={searchQuestion.trim().length < 8 || createSearch.isPending}>{createSearch.isPending ? "Starting search…" : "Search papers"}</button>{searchJob.data ? <div className="search-job-panel"><JobProgress job={searchJob.data} /><div className="job-controls">{searchJob.data.state === "running" ? <button onClick={() => controlSearch("pause")}>Pause</button> : null}{!terminalJobStates.has(searchJob.data.state) ? <button onClick={() => controlSearch("cancel")}>Cancel</button> : null}{["failed", "interrupted", "cancelled"].includes(searchJob.data.state) ? <button onClick={() => controlSearch("retry-failed")}>Retry</button> : null}</div><p>{previewRows.length} provisional paper{previewRows.length === 1 ? "" : "s"} visible. Existing saved results remain available below.</p></div> : null}</section>
      {(activeSearch || previewRows.length) ? <section><div className="drawer-section-heading"><div><span className="step-label">B · Preview and edit</span><h3>{textValue(displaySearch.query, textValue(displaySearch.goal, searchQuestion))}</h3><p>{selectedWorkIds.length} new selected · {newUsablePreviewIds.length} new usable · {alreadySavedCount} already in folder · {previewRows.length - usablePreviewIds.length} metadata-only</p></div>{searchRows.length ? <SmartSelect ariaLabel="Saved literature searches" value={activeSearchId} onChange={(value) => { const found = objectValue(searchRows.find((item) => textValue(item.search_id) === value)); setActiveSearchId(value); setPendingSearchId(""); setSelectedWorkIds(defaultNewWorkIds(found, destinationWorkIds)); }} placeholder="Saved searches…" options={searchRows.map((item) => ({ value: textValue(item.search_id), label: textValue(item.query, textValue(item.goal)), description: `${listValue(item.results).length} results` }))} /> : null}</div>{Boolean(displaySearch.selection_finalized) ? <div className="literature-selection-actions"><button onClick={() => setSelectedWorkIds(allUsableSelected ? selectedWorkIds.filter((id) => !newUsablePreviewIds.includes(id)) : Array.from(new Set([...selectedWorkIds, ...newUsablePreviewIds])))}>{allUsableSelected ? "Clear all new papers" : `Select all new (${newUsablePreviewIds.length})`}</button><span>Already-saved and metadata-only records cannot be acquired again.</span></div> : null}<div className="drawer-paper-list">{previewRows.map((paper) => { const workId = searchWorkId(paper); const checked = selectedWorkIds.includes(workId); const usable = searchWorkUsable(paper); const alreadySaved = destinationWorkIds.has(workId); return <label key={workId} className={`${checked ? "selected" : ""} ${usable && !alreadySaved ? "" : "disabled"}`}><input type="checkbox" checked={checked} disabled={!Boolean(displaySearch.selection_finalized) || !usable || alreadySaved} onChange={() => setSelectedWorkIds((current) => checked ? current.filter((id) => id !== workId) : [...current, workId])} /><span><strong>{textValue(paper.title)}</strong><small>{numberValue(paper.year) || "Year unknown"} · {publicationLabel(paper)}</small><small>{alreadySaved ? "Already in this folder" : listValue(paper.oa_locations).length ? "Open-access full text may be available" : textValue(paper.abstract).trim() ? "Permitted abstract fallback available" : "Metadata only · not extractable"}</small></span></label>; })}</div>{showingPendingSearch && activeRows.length ? <details className="saved-results"><summary>Keep viewing the previous saved preview ({activeRows.length} documents)</summary><ul>{activeRows.slice(0, 10).map((paper) => <li key={searchWorkId(paper)}>{textValue(paper.title)}</li>)}</ul></details> : null}{searchJob.data?.error && showingPendingSearch ? <ErrorState error={searchJob.data.error} retry={() => controlSearch("retry-failed")} /> : null}</section> : null}
      {activeSearch && !showingPendingSearch && Boolean(activeSearch.selection_finalized) ? <section><span className="step-label">C · Choose destination and acquire</span><div className="segmented destination-mode"><button className={destinationMode === "existing" ? "selected" : ""} onClick={() => setDestinationMode("existing")}>Add to existing folder</button><button className={destinationMode === "new" ? "selected" : ""} onClick={() => setDestinationMode("new")}>Create new folder</button></div>{destinationMode === "existing" ? <label><span>Private folder</span><SmartSelect ariaLabel="Acquisition destination folder" value={destinationSourceId} onChange={setDestinationSourceId} placeholder="Choose an existing folder…" options={sourceRows.map((source) => ({ value: source.source_id, label: source.display_name, description: `${source.document_count} indexed papers` }))} /></label> : <><label><span>New folder name</span><input value={acquisitionFolderName} onChange={(event) => setAcquisitionFolderName(event.target.value)} placeholder="e.g. test-ASD" /></label><p className="destination-receipt"><strong>Principia will create:</strong><code>{storageLayout.data ? `${storageLayout.data.local_data}/${acquisitionFolderName || "…"}` : `local_data/${acquisitionFolderName || "…"}`}</code></p></>}<div className="acquisition-contract"><strong>Raw data only</strong><span>{destinationMode === "existing" ? "Selected papers are added to the chosen folder and its inventory is refreshed." : "A new named folder is created under local_data."} Acquisition creates no Principles and makes no LLM call.</span></div><button className="primary full" onClick={() => acquire.mutate()} disabled={!selectedWorkIds.length || (destinationMode === "new" ? !acquisitionFolderName.trim() : !destinationSourceId) || acquire.isPending}>{acquire.isPending ? "Starting acquisition…" : `${destinationMode === "existing" ? "Add" : "Acquire"} ${selectedWorkIds.length} document${selectedWorkIds.length === 1 ? "" : "s"}`}</button>{acquisitionJob.data ? <div className="drawer-job"><JobProgress job={acquisitionJob.data} compact /></div> : null}</section> : null}
    </aside></div> : null}
  </div>;
}
