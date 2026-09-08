import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { ErrorState } from "../components/AsyncState";
import { CloudStatusControl } from "../components/CloudStatusControl";
import { JobProgress, terminalJobStates } from "../components/JobProgress";
import { ScientificText } from "../components/ScientificText";
import {
  ResearchGraph,
  type ResearchGraphEdgeSelection,
  type ResearchGraphItem,
  type ResearchGraphViewport,
} from "../components/ResearchGraph";
import {
  graphEdgeLayer,
  rankGraphSearchResults,
  type GraphEdgeLayer,
  type GraphEdgeLayerVisibility,
} from "../components/researchGraphControls";
import {
  queueGraphMutation,
  queuedGraphMutations,
  removeQueuedGraphMutation,
} from "../utils/graphRetryQueue";

type LocalSource = components["schemas"]["LocalSourceResponse"];
type Job = components["schemas"]["JobRecord"];
type UnknownRecord = Record<string, unknown>;
type Tray = "global" | "local" | "meta";
type Studio = "" | "connection" | "principle";

const INITIAL_ATLAS_VIEWPORT = {
  min_x: -10_000,
  max_x: 10_000,
  min_y: -10_000,
  max_y: 10_000,
  zoom: 0.55,
};

const EDGE_LAYER_OPTIONS: Array<{
  id: GraphEdgeLayer;
  label: string;
  title: string;
}> = [
  {
    id: "scientific",
    label: "Scientific links",
    title: "Reviewed Cloud relations and foundation links",
  },
  {
    id: "context",
    label: "Map context",
    title: "Navigation-only context, shared evidence, and semantic affinity",
  },
  {
    id: "virtual",
    label: "Virtual",
    title: "Unreviewed relationships derived in this research session",
  },
];

const clamp = (value: number, minimum: number, maximum: number): number =>
  Math.min(Math.max(value, minimum), Math.max(minimum, maximum));

const record = (value: unknown): UnknownRecord =>
  value !== null && typeof value === "object" ? (value as UnknownRecord) : {};
const text = (value: unknown): string =>
  typeof value === "string" ? value : "";
const rows = (value: unknown): UnknownRecord[] =>
  Array.isArray(value) ? value.map(record) : [];
const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.map(String) : [];
const providerIdentifier = (value: UnknownRecord): string =>
  text(value.provider_id) || text(value.provider);
const terminal = new Set([
  "succeeded",
  "partial",
  "failed",
  "cancelled",
  "interrupted",
]);
const onlineFolderName = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 56) || "public-literature";

function comparableText(value: string): string {
  return value
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "");
}

function distinctText(value: unknown, ...shown: string[]): string {
  const candidate = text(value).trim();
  if (!candidate) return "";
  const comparable = comparableText(candidate);
  return shown.some(
    (entry) => comparable && comparable === comparableText(entry),
  )
    ? ""
    : candidate;
}

function itemTitle(item: UnknownRecord): string {
  return (
    text(item.title) ||
    text(item.claim).slice(0, 90) ||
    text(item.principle_id) ||
    text(item.id)
  );
}

function uniquePublicSources(value: unknown): UnknownRecord[] {
  const unique = new Map<string, UnknownRecord>();
  for (const source of rows(value)) {
    const url =
      text(source.source_url) ||
      text(source.landing_url) ||
      strings(source.source_urls)[0] ||
      text(record(source.availability).full_text_url);
    const identity =
      text(source.work_id) ||
      text(source.doi).toLowerCase() ||
      url.toLowerCase() ||
      comparableText(text(source.title));
    if (!identity) continue;
    const previous = unique.get(identity);
    if (!previous) {
      unique.set(identity, source);
      continue;
    }
    const anchors = [
      ...rows(previous.evidence_anchors),
      ...rows(source.evidence_anchors),
    ].filter(
      (anchor, index, all) =>
        all.findIndex(
          (candidate) =>
            text(candidate.evidence_digest) === text(anchor.evidence_digest) &&
            Number(candidate.page ?? -1) === Number(anchor.page ?? -1) &&
            text(candidate.section) === text(anchor.section),
        ) === index,
    );
    unique.set(identity, {
      ...previous,
      ...source,
      source_url: text(previous.source_url) || text(source.source_url),
      evidence_anchors: anchors,
      evidence_anchor_count: Math.max(
        Number(previous.evidence_anchor_count ?? 0),
        Number(source.evidence_anchor_count ?? 0),
        anchors.length,
      ),
    });
  }
  return [...unique.values()];
}

function reliabilityScore(item: UnknownRecord): number {
  const explicit = Number(record(item.quality).reliability);
  if (Number.isFinite(explicit) && explicit > 0)
    return Math.round(Math.min(99, explicit <= 1 ? explicit * 100 : explicit));
  const maturity =
    (
      {
        established: 82,
        replicated: 78,
        supported: 67,
        contested: 46,
        unassessed: 42,
      } as Record<string, number>
    )[text(item.maturity)] ?? 48;
  const sources = uniquePublicSources(item.source_references).length;
  const structure = Math.min(
    8,
    strings(item.conditions).length * 2 +
      strings(item.boundary).length +
      (text(item.falsifier) ? 3 : 0),
  );
  return Math.min(
    97,
    maturity +
      Math.min(7, sources * 2) +
      structure +
      (item.review_status === "reviewed" ? 3 : 0),
  );
}

function influenceScore(item: UnknownRecord): number {
  const relations =
    rows(item.relations).length +
    rows(item.foundations).length +
    rows(item.linked_children).length;
  const sources = uniquePublicSources(item.source_references).length;
  const recognition = rows(item.recognition).length;
  return Math.min(
    99,
    28 +
      Math.round(Math.sqrt(relations) * 14) +
      Math.min(24, sources * 3) +
      Math.min(18, recognition * 6),
  );
}

function sessionGraphItem(
  value: UnknownRecord,
  index: number,
): ResearchGraphItem {
  const payload = record(value.payload);
  return {
    principle_id: text(value.principle_id) || text(value.id),
    record_kind:
      text(value.record_kind) ||
      (text(payload.principle_class) === "meta"
        ? "meta_principle"
        : "ordinary"),
    origin: text(value.origin) || "global_atlas",
    x: Number(value.x ?? 0),
    y: Number(value.y ?? 0),
    position_source: text(value.position_source) || "snapshot",
    z_index: Number(value.z_index ?? index),
    payload,
  };
}

export function ResearchWorkspacePage() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const revisionBySessionRef = useRef(new Map<string, number>());
  const saveChain = useRef(Promise.resolve());
  const hydratedSessionIdRef = useRef("");
  const launchedGoalRef = useRef("");
  const hydratedResultsRunRef = useRef("");
  const inspectorRef = useRef<HTMLElement | null>(null);
  const inspectorDragRef = useRef<{
    pointerId: number;
    x: number;
    y: number;
    originX: number;
    originY: number;
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);
  const inspectorResizeRef = useRef<{
    pointerId: number;
    x: number;
    y: number;
    width: number;
    height: number;
    left: number;
    top: number;
  } | null>(null);
  const optionsRef = useRef<HTMLDetailsElement | null>(null);
  const areaFilterRef = useRef<HTMLDetailsElement | null>(null);
  const mapFinderRef = useRef<HTMLDetailsElement | null>(null);
  const edgeLayersRef = useRef<HTMLDetailsElement | null>(null);
  const [goal, setGoal] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [confirmEgress, setConfirmEgress] = useState(false);
  const [providerProfile, setProviderProfile] = useState("siliconflow");
  const [providerKey, setProviderKey] = useState("");
  const [providerMessage, setProviderMessage] = useState("");
  const [model, setModel] = useState("deepseek-ai/DeepSeek-V4-Flash");
  const [selectedId, setSelectedId] = useState("");
  const [focusTarget, setFocusTarget] = useState<{
    id: string;
    request: number;
  } | null>(null);
  const [selectedEdge, setSelectedEdge] =
    useState<ResearchGraphEdgeSelection | null>(null);
  const [inspectorOffset, setInspectorOffset] = useState({ x: 0, y: 0 });
  const [inspectorSize, setInspectorSize] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [runNotice, setRunNotice] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [tray, setTray] = useState<Tray>("global");
  const [trayHidden, setTrayHidden] = useState(false);
  const [globalFinderOpen, setGlobalFinderOpen] = useState(false);
  const [globalQuery, setGlobalQuery] = useState("");
  const [globalSearchQuery, setGlobalSearchQuery] = useState("");
  const [globalFinderMessage, setGlobalFinderMessage] = useState("");
  const [mapQuery, setMapQuery] = useState("");
  const [mapFocusAnnouncement, setMapFocusAnnouncement] = useState("");
  const [visibleEdgeLayers, setVisibleEdgeLayers] =
    useState<GraphEdgeLayerVisibility>({
      scientific: true,
      context: true,
      virtual: true,
    });
  const [studio, setStudio] = useState<Studio>("");
  const [cart, setCart] = useState<string[]>([]);
  const [cartSearch, setCartSearch] = useState("");
  const [researchDirection, setResearchDirection] = useState("");
  const [studioMessage, setStudioMessage] = useState("");
  const [artifactDrawer, setArtifactDrawer] = useState<
    "" | "virtual_connection" | "virtual_principle"
  >("");
  const [virtualDeleteTarget, setVirtualDeleteTarget] = useState("");
  const [generatedPrinciples, setGeneratedPrinciples] = useState<
    UnknownRecord[]
  >([]);
  const [savedVirtualIds, setSavedVirtualIds] = useState<Record<string, string>>({});
  const [onlineOpen, setOnlineOpen] = useState(false);
  const [onlineGoal, setOnlineGoal] = useState("");
  const [onlineSearchId, setOnlineSearchId] = useState("");
  const [onlineJobId, setOnlineJobId] = useState("");
  const [onlineSelected, setOnlineSelected] = useState<string[]>([]);
  const [onlineAcquireJobId, setOnlineAcquireJobId] = useState("");
  const [atlasViewport, setAtlasViewport] = useState(INITIAL_ATLAS_VIEWPORT);
  const [selectedAtlasAreas, setSelectedAtlasAreas] = useState<string[]>([]);
  const closeArtifactDrawer = () => {
    setArtifactDrawer("");
    setVirtualDeleteTarget("");
  };

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const resize = inspectorResizeRef.current;
      if (resize?.pointerId === event.pointerId) {
        const maximumWidth = Math.min(720, window.innerWidth - resize.left - 12);
        const maximumHeight = window.innerHeight - resize.top - 12;
        setInspectorSize({
          width: clamp(
            resize.width + event.clientX - resize.x,
            320,
            maximumWidth,
          ),
          height: clamp(
            resize.height + event.clientY - resize.y,
            260,
            maximumHeight,
          ),
        });
        return;
      }
      const drag = inspectorDragRef.current;
      if (!drag || drag.pointerId !== event.pointerId) return;
      const commandBottom =
        document.querySelector(".research-command-bar")?.getBoundingClientRect()
          .bottom ?? 0;
      const nextLeft = clamp(
        drag.left + event.clientX - drag.x,
        10,
        window.innerWidth - drag.width - 10,
      );
      const nextTop = clamp(
        drag.top + event.clientY - drag.y,
        commandBottom + 10,
        window.innerHeight - drag.height - 10,
      );
      setInspectorOffset({
        x: drag.originX + nextLeft - drag.left,
        y: drag.originY + nextTop - drag.top,
      });
    };
    const finish = (event: PointerEvent) => {
      if (inspectorDragRef.current?.pointerId === event.pointerId)
        inspectorDragRef.current = null;
      if (inspectorResizeRef.current?.pointerId === event.pointerId)
        inspectorResizeRef.current = null;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
    };
  }, []);

  useEffect(() => {
    if (!selectedId && !selectedEdge) return;
    const closeOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const element = event.target as HTMLElement;
      const opensAnotherPrinciple = element.closest(
        ".research-graph-stage, .tray-preview, .derivation-studio, .artifact-drawer, .edge-endpoints, .inspector-foundation, .research-modal article > button:first-child",
      );
      if (!inspectorRef.current?.contains(target) && !opensAnotherPrinciple) {
        setSelectedId("");
        setSelectedEdge(null);
      }
    };
    document.addEventListener("click", closeOutside);
    return () => document.removeEventListener("click", closeOutside);
  }, [selectedId, selectedEdge]);

  useEffect(() => {
    if (!selectedId && !selectedEdge) return;
    window.requestAnimationFrame(() => {
      const scrollRegion = inspectorRef.current?.querySelector(
        ".inspector-scroll-region",
      );
      if (scrollRegion instanceof HTMLElement) scrollRegion.scrollTop = 0;
    });
  }, [selectedId, selectedEdge?.edge_id]);

  useEffect(() => {
    const closeOptions = (event: MouseEvent) => {
      if (
        optionsRef.current?.open &&
        !optionsRef.current.contains(event.target as Node)
      )
        optionsRef.current.open = false;
      if (
        areaFilterRef.current?.open &&
        !areaFilterRef.current.contains(event.target as Node)
      )
        areaFilterRef.current.open = false;
      if (
        mapFinderRef.current?.open &&
        !mapFinderRef.current.contains(event.target as Node)
      )
        mapFinderRef.current.open = false;
      if (
        edgeLayersRef.current?.open &&
        !edgeLayersRef.current.contains(event.target as Node)
      )
        edgeLayersRef.current.open = false;
    };
    document.addEventListener("click", closeOptions);
    return () => document.removeEventListener("click", closeOptions);
  }, []);

  useEffect(() => {
    if (!actionNotice) return;
    const timer = window.setTimeout(() => setActionNotice(""), 4_800);
    return () => window.clearTimeout(timer);
  }, [actionNotice]);

  const session = useQuery({
    queryKey: ["research-session", sessionId],
    enabled: Boolean(sessionId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/research-sessions/{session_id}", {
            params: { path: { session_id: sessionId } },
          }),
        ),
      ),
    refetchInterval: (query) =>
      terminal.has(text(record(query.state.data).state)) ? 3_000 : 700,
  });
  const activeRunId = text(session.data?.active_run_id);
  const activeRunState =
    text(record(session.data?.active_run).state) || text(session.data?.state);
  const graph = useQuery({
    queryKey: ["research-session-graph", sessionId],
    enabled: Boolean(sessionId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/research-sessions/{session_id}/graph", {
            params: { path: { session_id: sessionId } },
          }),
        ),
      ),
    refetchInterval:
      Boolean(sessionId) && !terminal.has(activeRunState) ? 1_000 : false,
  });
  const cloudAtlas = useQuery({
    queryKey: [
      "global-webgl-atlas",
      selectedAtlasAreas.join("|"),
      atlasViewport,
    ],
    enabled: !sessionId,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/cloud/graph/viewport", {
            params: {
              query: {
                ...atlasViewport,
                areas: selectedAtlasAreas.join(","),
                q: "",
                limit: 96,
              },
            },
          }),
        ),
      ),
    staleTime: 60_000,
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === selectedAtlasAreas.join("|")
        ? previous
        : undefined,
  });
  const cloudAtlasAreas = useQuery({
    queryKey: ["global-webgl-atlas-areas"],
    enabled: !sessionId,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/cloud/graph/viewport", {
            params: {
              query: {
                min_x: -10_000,
                max_x: 10_000,
                min_y: -10_000,
                max_y: 10_000,
                zoom: 0.1,
                areas: "",
                q: "",
                limit: 200,
              },
            },
          }),
        ),
      ),
    staleTime: 5 * 60_000,
  });
  const sources = useQuery({
    queryKey: ["research-sources"],
    queryFn: async () =>
      dataOrThrow(await api.GET("/api/v1/local/sources", {})),
    refetchInterval: 2_000,
  });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: async () =>
      record(dataOrThrow(await api.GET("/api/v1/providers", {}))),
  });
  const cloud = useQuery({
    queryKey: ["cloud-status"],
    queryFn: async () =>
      record(dataOrThrow(await api.GET("/api/v1/cloud/status", {}))),
    refetchInterval: 15_000,
    refetchOnWindowFocus: "always",
  });
  const refreshCloud = useMutation({
    mutationFn: async () =>
      record(
        dataOrThrow(
          await api.POST("/api/v1/cloud/sync", {
            params: { query: { force: true } },
          }),
        ),
      ),
    onSuccess: async () => {
      await cloud.refetch();
      queryClient.invalidateQueries({ queryKey: ["global-webgl-atlas"] });
      queryClient.invalidateQueries({
        queryKey: ["global-webgl-atlas-areas"],
      });
    },
  });
  const trayPage = useQuery({
    queryKey: ["research-results", sessionId, activeRunId, tray],
    enabled: Boolean(sessionId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/research-sessions/{session_id}/results", {
            params: {
              path: { session_id: sessionId },
              query: { membership: tray, limit: 200, offset: 0 },
            },
          }),
        ),
      ),
    refetchOnMount: "always",
    refetchInterval: !terminal.has(activeRunState) ? 700 : false,
  });
  const artifacts = useQuery({
    queryKey: ["research-artifacts", sessionId],
    enabled: Boolean(sessionId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/research-sessions/{session_id}/artifacts", {
            params: { path: { session_id: sessionId } },
          }),
        ),
      ),
  });
  const localVirtualLibrary = useQuery({
    queryKey: ["local-virtual-principles", sessionId],
    enabled: Boolean(sessionId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/principles", {
            params: {
              query: {
                scope: "local",
                virtual_only: true,
                evidence_status: "",
                limit: 100,
                page: 1,
              },
            },
          }),
        ),
      ),
  });
  const allTrayPages = ["global", "local", "meta"].map((membership) =>
    useQuery({
      queryKey: ["research-results", sessionId, activeRunId, membership],
      enabled: Boolean(sessionId) && Boolean(studio),
      queryFn: async () =>
        record(
          dataOrThrow(
            await api.GET("/api/v1/research-sessions/{session_id}/results", {
              params: {
                path: { session_id: sessionId },
                query: {
                  membership: membership as Tray,
                  limit: 200,
                  offset: 0,
                },
              },
            }),
          ),
        ),
    }),
  );
  const globalFinder = useQuery({
    queryKey: ["add-global-principles", globalSearchQuery],
    enabled: globalFinderOpen && globalSearchQuery.length >= 3,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.POST("/api/v1/cloud/search", {
            body: {
              entity: "all",
              query: globalSearchQuery,
              areas: [],
              venues: [],
              institutions: [],
              full_text_status: "",
              cursor: "",
              limit: 40,
              paper_cohort: 100,
            },
          }),
        ),
      ),
  });
  const submitGlobalFinderSearch = () => {
    const query = globalQuery.trim();
    if (query.length < 3) {
      setGlobalFinderMessage(
        "Enter at least three characters to search the Cloud.",
      );
      return;
    }
    setGlobalFinderMessage("");
    if (query === globalSearchQuery) void globalFinder.refetch();
    else setGlobalSearchQuery(query);
  };
  const selectedDetail = useQuery({
    queryKey: ["research-selected-cloud-detail", selectedId],
    enabled:
      selectedId.startsWith("prn:") ||
      selectedId.startsWith("meta:") ||
      selectedId.startsWith("cand:"),
    queryFn: async () =>
      record(
        dataOrThrow(
          selectedId.startsWith("cand:")
            ? await api.GET("/api/v1/local/candidates/{candidate_id}", {
                params: { path: { candidate_id: selectedId } },
              })
            : selectedId.startsWith("meta:")
            ? await api.GET("/api/v1/cloud/meta-principles/{principle_id}", {
                params: { path: { principle_id: selectedId } },
              })
            : await api.GET("/api/v1/cloud/principles/{principle_id}", {
                params: { path: { principle_id: selectedId } },
              }),
        ),
      ),
  });
  const onlineSearchJob = useQuery({
    queryKey: ["job", onlineJobId],
    enabled: Boolean(onlineJobId),
    queryFn: async () =>
      dataOrThrow(
        await api.GET("/api/v1/jobs/{job_id}", {
          params: { path: { job_id: onlineJobId } },
        }),
      ) as Job,
    refetchInterval: (query) =>
      terminalJobStates.has(text(record(query.state.data).state)) ? false : 700,
  });
  const onlineSearch = useQuery({
    queryKey: ["online-search", onlineSearchId],
    enabled: Boolean(onlineSearchId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/local/literature-searches/{search_id}", {
            params: { path: { search_id: onlineSearchId } },
          }),
        ),
      ),
    refetchInterval: (query) =>
      Boolean(record(query.state.data).selection_finalized) ? false : 700,
  });
  const onlineAcquireJob = useQuery({
    queryKey: ["job", onlineAcquireJobId],
    enabled: Boolean(onlineAcquireJobId),
    queryFn: async () =>
      dataOrThrow(
        await api.GET("/api/v1/jobs/{job_id}", {
          params: { path: { job_id: onlineAcquireJobId } },
        }),
      ) as Job,
    refetchInterval: (query) =>
      terminalJobStates.has(text(record(query.state.data).state)) ? false : 700,
  });

  const providerRows = rows(providers.data?.profiles);
  const profile = record(
    providerRows.find((item) => providerIdentifier(item) === providerProfile) ??
      providerRows[0],
  );
  const sourceRows: LocalSource[] = sources.data?.sources ?? [];
  const graphRows = useMemo(
    () =>
      sessionId
        ? rows(graph.data?.items).map(sessionGraphItem)
        : rows(cloudAtlas.data?.nodes).map((item, index) =>
            sessionGraphItem(
              { ...item, principle_id: item.id, payload: item },
              index,
            ),
          ),
    [sessionId, graph.dataUpdatedAt, cloudAtlas.dataUpdatedAt],
  );
  const mapSearchableRows = useMemo(
    () => graphRows.filter((item) => item.record_kind !== "area"),
    [graphRows],
  );
  const mapSearchableCount = mapSearchableRows.length;
  const mapTitleCoverage = mapSearchableRows.filter((item) =>
    Boolean(text(item.payload.title)),
  ).length;
  const mapClaimCoverage = mapSearchableRows.filter(
    (item) =>
      Boolean(text(item.payload.claim)) || Boolean(text(item.payload.argument)),
  ).length;
  const mapSearchCoverageComplete =
    mapSearchableCount > 0 &&
    mapTitleCoverage === mapSearchableCount &&
    mapClaimCoverage === mapSearchableCount;
  const mapSearchResults = useMemo(
    () => rankGraphSearchResults(mapSearchableRows, mapQuery),
    [mapSearchableRows, mapQuery],
  );
  const atlasAreas = useMemo(
    () =>
      rows(cloudAtlasAreas.data?.areas).sort(
        (left, right) =>
          Number(right.principle_count ?? 0) -
            Number(left.principle_count ?? 0) ||
          text(left.display_name).localeCompare(text(right.display_name)),
      ),
    [cloudAtlasAreas.dataUpdatedAt],
  );
  const selectedGraphItem = graphRows.find(
    (item) => item.principle_id === selectedId,
  );
  const selectedEdgeLayer = selectedEdge
    ? graphEdgeLayer(selectedEdge.edge_class)
    : null;
  const graphIds = new Set(graphRows.map((item) => item.principle_id));
  const graphInsertionPosition = (identifier: string, offset = 0) => {
    const visible = graphRows.filter((item) => item.record_kind !== "area");
    const centerX = visible.length
      ? visible.reduce((sum, item) => sum + item.x, 0) / visible.length
      : 0;
    const centerY = visible.length
      ? visible.reduce((sum, item) => sum + item.y, 0) / visible.length
      : 0;
    let seed = 0;
    for (const character of identifier)
      seed = (seed * 31 + character.charCodeAt(0)) >>> 0;
    const angle = (seed % 6283) / 1000 + offset * 0.68;
    const radius = 210 + Math.sqrt(visible.length + offset + 1) * 34;
    return {
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius,
    };
  };
  const focusGraphItem = (identifier: string, announcedTitle?: string) => {
    const item = mapSearchableRows.find(
      (candidate) => candidate.principle_id === identifier,
    );
    const title = announcedTitle || itemTitle(item?.payload ?? {});
    setMapFocusAnnouncement("");
    setSelectedEdge(null);
    setSelectedId(identifier);
    setFocusTarget({ id: identifier, request: Date.now() });
    if (mapFinderRef.current) mapFinderRef.current.open = false;
    window.requestAnimationFrame(() => {
      setMapFocusAnnouncement(
        `Focused ${title || identifier}. Principle details opened.`,
      );
      inspectorRef.current?.focus({ preventScroll: true });
    });
  };
  const toggleEdgeLayer = (layer: GraphEdgeLayer) => {
    const willHide = visibleEdgeLayers[layer];
    setVisibleEdgeLayers((current) => ({
      ...current,
      [layer]: !current[layer],
    }));
    if (
      willHide &&
      selectedEdge &&
      graphEdgeLayer(selectedEdge.edge_class) === layer
    )
      setSelectedEdge(null);
  };
  const sessionTheme =
    text(graph.data?.theme) === "deep-space" ? "deep-space" : "daylight";
  const persistedViewport = record(graph.data?.viewport);
  const trayItems = rows(trayPage.data?.items);
  const cartCandidates = useMemo(
    () =>
      allTrayPages
        .flatMap((page) => rows(page.data?.items))
        .filter((item, index, source) => {
          const id =
            text(item.id) || text(item.principle_id) || text(item.candidate_id);
          return (
            id &&
            source.findIndex(
              (other) =>
                (text(other.id) ||
                  text(other.principle_id) ||
                  text(other.candidate_id)) === id,
            ) === index
          );
        }),
    [allTrayPages.map((page) => page.dataUpdatedAt).join("|")],
  );
  const principleCatalog = useMemo(() => {
    const candidates: UnknownRecord[] = [
      ...graphRows.map((item) => ({
        ...item.payload,
        id: item.principle_id,
        principle_id: item.principle_id,
        principle_class:
          item.record_kind === "meta_principle" ? "meta" : "literature",
      }) as UnknownRecord),
      ...cartCandidates,
      ...trayItems,
      ...rows(globalFinder.data?.items),
    ];
    return candidates.filter((item, index, source) => {
      const id =
        text(item.id) || text(item.principle_id) || text(item.candidate_id);
      return (
        Boolean(id) &&
        source.findIndex(
          (other) =>
            (text(other.id) ||
              text(other.principle_id) ||
              text(other.candidate_id)) === id,
        ) === index
      );
    });
  }, [graphRows, cartCandidates, trayItems, globalFinder.dataUpdatedAt]);
  const selectedExternal = [...principleCatalog].find(
    (item) =>
      (text(item.id) || text(item.principle_id) || text(item.candidate_id)) ===
      selectedId,
  );
  const selectedDetailPayload = record(selectedDetail.data);
  const selectedBase =
    selectedGraphItem ??
    (selectedExternal
      ? sessionGraphItem(
          {
            principle_id: selectedId,
            record_kind:
              text(selectedExternal.principle_class) === "meta"
                ? "meta_principle"
                : "ordinary",
            payload: selectedExternal,
          },
          0,
        )
      : Object.keys(selectedDetailPayload).length
        ? sessionGraphItem(
            {
              principle_id: selectedId,
              record_kind:
                text(selectedDetailPayload.principle_class) === "meta"
                  ? "meta_principle"
                  : "ordinary",
              payload: selectedDetailPayload,
            },
            0,
          )
        : undefined);
  const selected =
    selectedBase && Object.keys(selectedDetailPayload).length
      ? { ...selectedBase, payload: selectedDetailPayload }
      : selectedBase;
  const selectedSourcesForDisplay = selected
    ? uniquePublicSources(selected.payload.source_references)
    : [];
  const selectedClaim = selected
    ? text(selected.payload.claim) || text(selected.payload.argument)
    : "";
  const selectedArgument = selected
    ? distinctText(selected.payload.argument, selectedClaim)
    : "";
  const selectedArgumentForDisplay = selectedArgument || selectedClaim;
  const selectedInterpretation = selected
    ? distinctText(
        selected.payload.interpretation,
        selectedClaim,
        selectedArgument,
      )
    : "";
  const artifactRows = useMemo(
    () => rows(artifacts.data?.items),
    [artifacts.dataUpdatedAt],
  );
  const virtualPrincipleItems = useMemo(() => {
    const merged = new Map<string, UnknownRecord>();
    for (const artifact of [...artifactRows].reverse()) {
      if (text(artifact.kind) !== "virtual_principle") continue;
      for (const item of rows(record(artifact.payload).items)) {
        const proposal = record(item.proposal);
        const key =
          text(item.virtual_id) ||
          text(item.candidate_id) ||
          comparableText(`${itemTitle(proposal)}:${text(proposal.claim)}`);
        if (!key) continue;
        const previous = merged.get(key) ?? {};
        merged.set(key, {
          ...previous,
          ...item,
          proposal: { ...record(previous.proposal), ...proposal },
        });
      }
    }
    return [...merged.values()];
  }, [artifactRows]);
  const savedVirtualCandidates = useMemo(() => {
    const mapped: Record<string, string> = { ...savedVirtualIds };
    for (const item of virtualPrincipleItems) {
      const key = text(item.virtual_id);
      const candidateId = text(item.candidate_id);
      if (key && candidateId) mapped[key] = candidateId;
    }
    for (const graphItem of graphRows.filter(
      (item) => item.origin === "virtual_principle",
    )) {
      const graphFingerprint = comparableText(
        `${itemTitle(graphItem.payload)}:${text(graphItem.payload.claim)}`,
      );
      const match = virtualPrincipleItems.find((item) => {
        const proposal = record(item.proposal);
        return (
          comparableText(`${itemTitle(proposal)}:${text(proposal.claim)}`) ===
          graphFingerprint
        );
      });
      const virtualId = text(match?.virtual_id);
      if (virtualId) mapped[virtualId] = graphItem.principle_id;
    }
    for (const candidate of rows(localVirtualLibrary.data?.items)) {
      const fingerprint = comparableText(
        `${itemTitle(candidate)}:${text(candidate.claim)}`,
      );
      const match = virtualPrincipleItems.find((item) => {
        const proposal = record(item.proposal);
        return (
          comparableText(`${itemTitle(proposal)}:${text(proposal.claim)}`) ===
          fingerprint
        );
      });
      const virtualId = text(match?.virtual_id);
      const candidateId = text(candidate.id) || text(candidate.candidate_id);
      if (virtualId && candidateId) mapped[virtualId] = candidateId;
    }
    return mapped;
  }, [
    virtualPrincipleItems,
    savedVirtualIds,
    graphRows,
    localVirtualLibrary.dataUpdatedAt,
  ]);
  const virtualConnectionItems = useMemo(() => {
    const merged = new Map<string, UnknownRecord>();
    for (const artifact of artifactRows) {
      if (text(artifact.kind) !== "virtual_connection") continue;
      for (const item of rows(record(artifact.payload).items)) {
        const key =
          text(item.relation_id) ||
          `${text(item.source)}:${text(item.target)}:${text(item.relation_type)}`;
        if (key) merged.set(key, item);
      }
    }
    return [...merged.values()];
  }, [artifactRows]);
  const virtualEdges = useMemo(
    () => virtualConnectionItems,
    [virtualConnectionItems],
  );
  const edgeSource = selectedEdge
    ? graphRows.find((item) => item.principle_id === selectedEdge.source_id)
    : undefined;
  const edgeTarget = selectedEdge
    ? graphRows.find((item) => item.principle_id === selectedEdge.target_id)
    : undefined;
  const relatedMetaPrinciples = useMemo(() => {
    if (!selected || selected.record_kind === "meta_principle") return [];
    const related = new Map<
      string,
      { id: string; meta: UnknownRecord; relationType: string; rationale: string; reviewed: boolean }
    >();
    for (const foundation of rows(selected.payload.foundations)) {
      const link = record(foundation.link);
      const meta = record(foundation.meta_principle);
      const id =
        text(meta.id) ||
        text(meta.principle_id) ||
        text(foundation.meta_principle_id) ||
        text(link.meta_principle_id);
      if (!id) continue;
      related.set(id, {
        id,
        meta,
        relationType:
          text(foundation.relation_type) || text(link.relation_type) || "foundation",
        rationale: text(foundation.rationale) || text(link.rationale),
        reviewed: true,
      });
    }
    for (const edge of [...rows(graph.data?.edges), ...virtualEdges]) {
      const source = text(edge.source) || text(edge.source_principle_id);
      const target = text(edge.target) || text(edge.target_principle_id);
      if (source !== selected.principle_id && target !== selected.principle_id)
        continue;
      const otherId = source === selected.principle_id ? target : source;
      const graphItem = graphRows.find((item) => item.principle_id === otherId);
      if (!graphItem || graphItem.record_kind !== "meta_principle") continue;
      const previous = related.get(otherId);
      related.set(otherId, {
        id: otherId,
        meta: graphItem.payload,
        relationType:
          previous?.relationType ||
          text(edge.relation_type) ||
          text(edge.edge_class) ||
          "related foundation",
        rationale: previous?.rationale || text(edge.rationale),
        reviewed:
          previous?.reviewed || text(edge.edge_class) === "foundation",
      });
    }
    // ResearchGraph also draws one bounded semantic-context bridge for sparse
    // constellations. Mirror that visible bridge in the inspector so an edge
    // is never present without an inspectable Meta endpoint.
    const nearestVisibleMeta = graphRows
      .filter((item) => item.record_kind === "meta_principle")
      .sort((left, right) => {
        const sameAreaLeft =
          text(left.payload.area) === text(selected.payload.area) ? 0 : 1;
        const sameAreaRight =
          text(right.payload.area) === text(selected.payload.area) ? 0 : 1;
        return (
          sameAreaLeft - sameAreaRight ||
          Math.hypot(left.x - selected.x, left.y - selected.y) -
            Math.hypot(right.x - selected.x, right.y - selected.y)
        );
      })[0];
    if (nearestVisibleMeta && !related.has(nearestVisibleMeta.principle_id))
      related.set(nearestVisibleMeta.principle_id, {
        id: nearestVisibleMeta.principle_id,
        meta: nearestVisibleMeta.payload,
        relationType: "semantic foundation context",
        rationale:
          "This Meta-Principle is the nearest compatible foundation context in the current research map.",
        reviewed: false,
      });
    return [...related.values()];
  }, [
    selected?.principle_id,
    selectedDetail.dataUpdatedAt,
    graph.dataUpdatedAt,
    virtualEdges,
    graphRows,
  ]);

  useEffect(() => {
    const remoteRevision = Number(graph.data?.revision);
    if (Number.isFinite(remoteRevision))
      revisionBySessionRef.current.set(
        sessionId,
        Math.max(
          revisionBySessionRef.current.get(sessionId) ?? 0,
          remoteRevision,
        ),
      );
  }, [sessionId, graph.dataUpdatedAt]);

  useEffect(() => {
    if (!sessionId) {
      if (hydratedSessionIdRef.current) {
        hydratedSessionIdRef.current = "";
        setGoal("");
        setSelectedSources([]);
        setSelectedId("");
        setTray("global");
        setTrayHidden(false);
      }
      return;
    }
    if (!session.data || hydratedSessionIdRef.current === sessionId) return;
    const active = record(session.data.active_run);
    hydratedSessionIdRef.current = sessionId;
    setGoal(text(active.goal));
    setSelectedSources(strings(session.data.source_ids));
    setSelectedId("");
    setTray("global");
    setTrayHidden(false);
    if (text(session.data.provider_profile_id))
      setProviderProfile(text(session.data.provider_profile_id));
    if (text(session.data.model)) setModel(text(session.data.model));
  }, [sessionId, session.dataUpdatedAt]);

  useEffect(() => {
    const applyProviderModel = (event: Event) => {
      const detail = (event as CustomEvent<{ providerId?: string; model?: string }>).detail;
      if (detail?.providerId) setProviderProfile(detail.providerId);
      if (detail?.model) setModel(detail.model);
    };
    window.addEventListener("principia:provider-model-selected", applyProviderModel);
    return () =>
      window.removeEventListener(
        "principia:provider-model-selected",
        applyProviderModel,
      );
  }, []);

  const createSession = useMutation({
    mutationFn: async () =>
      record(
        dataOrThrow(
          await api.POST("/api/v1/research-sessions", {
            params: {
              query: {
                egress_confirmed: selectedSources.length
                  ? confirmEgress
                  : false,
              },
            },
            body: {
              title: "",
              project_id: null,
              run: {
                goal: goal.trim(),
                source_ids: selectedSources,
                include_global: true,
                include_online: false,
                provider_profile_id: providerProfile,
                model,
                local_limit: 20,
                global_limit: 50,
              },
            },
          }),
        ),
      ),
    onSuccess: (value) =>
      navigate(`/research/${encodeURIComponent(text(value.session_id))}`),
  });
  const startAnotherRun = useMutation({
    mutationFn: async () =>
      dataOrThrow(
        await api.POST("/api/v1/research-sessions/{session_id}/runs", {
          params: {
            path: { session_id: sessionId },
            query: {
              egress_confirmed: selectedSources.length ? confirmEgress : false,
            },
          },
          body: {
            goal: goal.trim(),
            source_ids: selectedSources,
            include_global: true,
            include_online: false,
            provider_profile_id: providerProfile,
            model,
            local_limit: 20,
            global_limit: 50,
          },
        }),
      ),
    onMutate: () => {
      launchedGoalRef.current = goal.trim();
      setRunNotice(
        "Searching the Global Cloud and starting the selected local branches…",
      );
      setTray("global");
      setTrayHidden(false);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["research-session", sessionId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["research-session-graph", sessionId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["research-results", sessionId],
      });
      setRunNotice(
        "New search started. Previous results remain available while new matches arrive.",
      );
    },
    onError: () =>
      setRunNotice(
        "The new search could not start. Your existing graph and results were preserved.",
      ),
  });
  const addFolders = useMutation({
    mutationFn: async () =>
      dataOrThrow(await api.POST("/api/v1/local/folder-picker/multiple", {})),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["research-sources"] }),
  });
  const disconnectFolder = useMutation({
    mutationFn: async (sourceId: string) =>
      dataOrThrow(
        await api.DELETE("/api/v1/library/collections/{kind}/{collection_id}", {
          params: { path: { kind: "source", collection_id: sourceId } },
        }),
      ),
    onSuccess: (_, sourceId) => {
      setSelectedSources((current) => current.filter((id) => id !== sourceId));
      queryClient.invalidateQueries({ queryKey: ["research-sources"] });
    },
  });
  const saveProviderKey = useMutation({
    mutationFn: async () => {
      await dataOrThrow(
        await api.PUT("/api/v1/provider-profiles/{provider_id}/credential", {
          params: { path: { provider_id: providerProfile } },
          body: { api_key: providerKey },
        }),
      );
      const connection = record(
        dataOrThrow(
          await api.POST("/api/v1/provider-profiles/{provider_id}/test", {
            params: { path: { provider_id: providerProfile } },
          }),
        ),
      );
      if (!Boolean(connection.ok)) {
        if (text(connection.category) === "authentication") {
          await api.DELETE(
            "/api/v1/provider-profiles/{provider_id}/credential",
            { params: { path: { provider_id: providerProfile } } },
          );
          throw new Error(
            "SiliconFlow rejected this key at both authorized endpoints. Please check the key and enter it again.",
          );
        }
        throw new Error(
          text(connection.category) === "rate_limited"
            ? "The key was accepted, but SiliconFlow is rate-limiting requests. Try again shortly."
            : "The key was saved, but SiliconFlow could not be reached. Check the network and try again.",
        );
      }
      return connection;
    },
    onSuccess: (connection) => {
      setProviderKey("");
      setProviderMessage(
        `Provider connected and verified through ${text(connection.base_url) || "an authorized endpoint"}.`,
      );
      queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  const applyGraphOperationsOptimistically = (
    operations: Array<Record<string, unknown>>,
  ) => {
    if (!sessionId || !operations.length) return;
    queryClient.setQueryData<UnknownRecord>(
      ["research-session-graph", sessionId],
      (currentValue) => {
        const current = record(currentValue);
        if (!Object.keys(current).length) return currentValue;
        let nextItems = rows(current.items).map((item) => ({ ...item }));
        let nextViewport = record(current.viewport);
        let nextTheme = text(current.theme) || "daylight";
        let changed = false;
        for (const operation of operations) {
          const action = text(operation.action);
          const identifier = text(operation.principle_id);
          if (action === "add" && identifier) {
            const index = nextItems.findIndex(
              (item) => text(item.principle_id) === identifier,
            );
            const previous = index >= 0 ? nextItems[index] : {};
            const payload = {
              ...record(previous.payload),
              ...record(operation.payload),
            };
            const optimisticItem: UnknownRecord = {
              ...previous,
              principle_id: identifier,
              record_kind:
                text(payload.principle_class) === "meta"
                  ? "meta_principle"
                  : "ordinary",
              origin: text(operation.origin) || text(previous.origin) || "add_global",
              x: Number(operation.x ?? previous.x ?? 0),
              y: Number(operation.y ?? previous.y ?? 0),
              position_source: "user",
              z_index:
                index >= 0
                  ? Number(previous.z_index ?? index)
                  : nextItems.reduce(
                      (maximum, item) =>
                        Math.max(maximum, Number(item.z_index ?? 0)),
                      -1,
                    ) + 1,
              payload,
            };
            if (index >= 0) nextItems[index] = optimisticItem;
            else nextItems = [...nextItems, optimisticItem];
            changed = true;
          } else if (action === "remove" && identifier) {
            const filtered = nextItems.filter(
              (item) => text(item.principle_id) !== identifier,
            );
            changed = changed || filtered.length !== nextItems.length;
            nextItems = filtered;
          } else if (action === "move" && identifier) {
            // Sigma has already moved this node in its graph. Mirroring the
            // move into React Query would restart the layout worker, briefly
            // clear the canvas, and regenerate context edges during a drag.
            continue;
          } else if (action === "viewport") {
            // Sigma already owns the live camera. Updating React Query here
            // would rebuild the graph after every pan/zoom settle and make
            // direct manipulation feel sticky.
            continue;
          } else if (action === "theme") {
            nextTheme = text(operation.theme) || nextTheme;
            changed = true;
          }
        }
        return changed
          ? {
              ...current,
              items: nextItems,
              viewport: nextViewport,
              theme: nextTheme,
            }
          : currentValue;
      },
    );
  };

  const sendGraphOperations = (
    operations: Array<Record<string, unknown>>,
  ): Promise<void> => {
    if (!sessionId || !operations.length) return Promise.resolve();
    const targetSessionId = sessionId;
    applyGraphOperationsOptimistically(operations);
    const next = saveChain.current
      .catch(() => undefined)
      .then(async () => {
        const expectedRevision =
          revisionBySessionRef.current.get(targetSessionId) ?? 0;
        try {
          const receipt = record(
            dataOrThrow(
              await api.PATCH("/api/v1/research-sessions/{session_id}/graph", {
                params: { path: { session_id: targetSessionId } },
                body: { expected_revision: expectedRevision, operations },
              }),
            ),
          );
          revisionBySessionRef.current.set(
            targetSessionId,
            Number(receipt.revision ?? expectedRevision + 1),
          );
          if (
            operations.some((operation) =>
              ["add", "remove"].includes(text(operation.action)),
            )
          )
            void queryClient.invalidateQueries({
              queryKey: ["research-session-graph", targetSessionId],
            });
        } catch (error) {
          await queueGraphMutation({
            sessionId: targetSessionId,
            expectedRevision,
            operations,
          });
          throw error;
        }
      });
    saveChain.current = next.catch(() => undefined);
    return next;
  };

  const addOrRevealPrinciple = async (
    item: UnknownRecord,
    present: boolean,
  ) => {
    const id =
      text(item.id) || text(item.principle_id) || text(item.candidate_id);
    if (!id) return;
    setActionNotice(
      present
        ? "Opening the Principle already on this graph…"
        : "Adding the Principle to this graph…",
    );
    try {
      if (!present) {
        const position = graphInsertionPosition(id);
        const save = sendGraphOperations([
          {
            action: "add",
            principle_id: id,
            payload: item,
            origin: "add_global",
            ...position,
          },
        ]);
        setFocusTarget({ id, request: Date.now() });
        await save;
      }
      setSelectedEdge(null);
      if (present) setFocusTarget({ id, request: Date.now() });
      if (present) {
        setSelectedId(id);
        setGlobalFinderOpen(false);
      }
      setActionNotice(
        present
          ? "This Principle was already on the graph; its details are now open."
          : "Principle added and centered. Keep searching, or close this panel to inspect the map.",
      );
      if (!present)
        setGlobalFinderMessage(
          "Added to the graph and centered. You can continue adding more Principles.",
        );
    } catch {
      setActionNotice(
        "The change is safely queued and will retry when the workspace reconnects.",
      );
    }
  };

  const beginInspectorDrag = (event: ReactPointerEvent<HTMLElement>) => {
    const bounds = inspectorRef.current?.getBoundingClientRect();
    if (!bounds) return;
    inspectorDragRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      originX: inspectorOffset.x,
      originY: inspectorOffset.y,
      left: bounds.left,
      top: bounds.top,
      width: bounds.width,
      height: bounds.height,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  const beginInspectorResize = (event: ReactPointerEvent<HTMLElement>) => {
    const bounds = inspectorRef.current?.getBoundingClientRect();
    if (!bounds) return;
    inspectorResizeRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      width: bounds.width,
      height: bounds.height,
      left: bounds.left,
      top: bounds.top,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.stopPropagation();
    event.preventDefault();
  };

  const toggleAtlasArea = (area: string) => {
    setSelectedId("");
    setSelectedEdge(null);
    setAtlasViewport(INITIAL_ATLAS_VIEWPORT);
    setSelectedAtlasAreas((current) =>
      current.includes(area)
        ? current.filter((value) => value !== area)
        : [...current, area].sort(),
    );
  };

  const requestProviderSetup = () => {
    setStudioMessage(
      "Connect an LLM provider to continue. Your selection and research session will remain exactly as they are.",
    );
    window.dispatchEvent(
      new CustomEvent("principia:open-provider-settings", {
        detail: { providerId: providerProfile, model },
      }),
    );
  };

  const openFoundation = async (
    metaId: string,
    metaPayload: UnknownRecord,
  ) => {
    if (!metaId) return;
    setSelectedEdge(null);
    if (sessionId && !graphIds.has(metaId)) {
      const anchor = selectedGraphItem;
      try {
        const save = sendGraphOperations([
          {
            action: "add",
            principle_id: metaId,
            payload: metaPayload,
            origin: `foundation:${selected?.principle_id || "inspector"}`,
            x: Number(anchor?.x ?? 0) + 105,
            y: Number(anchor?.y ?? 0) - 82,
          },
        ]);
        setFocusTarget({ id: metaId, request: Date.now() });
        await save;
        setActionNotice(
          "The Meta-Principle was added beside its literature Principle and opened.",
        );
      } catch {
        setActionNotice(
          "The Meta-Principle details are open. Its graph placement is queued until the workspace reconnects.",
        );
      }
    }
    setSelectedId(metaId);
    setFocusTarget({ id: metaId, request: Date.now() });
  };

  const settleViewport = (viewport: ResearchGraphViewport) => {
    if (sessionId) {
      sendGraphOperations([
        {
          action: "viewport",
          viewport: {
            x: viewport.x,
            y: viewport.y,
            angle: viewport.angle,
            ratio: viewport.ratio,
          },
        },
      ]);
      return;
    }
    const paddingX = Math.max(120, (viewport.max_x - viewport.min_x) * 0.18);
    const paddingY = Math.max(120, (viewport.max_y - viewport.min_y) * 0.18);
    const next = {
      min_x: viewport.min_x - paddingX,
      max_x: viewport.max_x + paddingX,
      min_y: viewport.min_y - paddingY,
      max_y: viewport.max_y + paddingY,
      zoom: viewport.zoom,
    };
    setAtlasViewport((current) => {
      const span = Math.max(
        1,
        current.max_x - current.min_x,
        current.max_y - current.min_y,
      );
      const moved = Math.max(
        Math.abs(current.min_x - next.min_x),
        Math.abs(current.max_x - next.max_x),
        Math.abs(current.min_y - next.min_y),
        Math.abs(current.max_y - next.max_y),
      );
      const zoomed =
        Math.abs(current.zoom - next.zoom) / Math.max(0.01, current.zoom);
      return moved / span < 0.04 && zoomed < 0.04 ? current : next;
    });
  };

  useEffect(() => {
    if (!sessionId) return;
    const flush = async () => {
      for (const queued of await queuedGraphMutations(sessionId)) {
        try {
          const receipt = record(
            dataOrThrow(
              await api.PATCH("/api/v1/research-sessions/{session_id}/graph", {
                params: { path: { session_id: sessionId } },
                body: {
                  expected_revision:
                    revisionBySessionRef.current.get(sessionId) ?? 0,
                  operations: queued.operations,
                },
              }),
            ),
          );
          revisionBySessionRef.current.set(
            sessionId,
            Number(
              receipt.revision ??
                (revisionBySessionRef.current.get(sessionId) ?? 0) + 1,
            ),
          );
          await removeQueuedGraphMutation(queued.id);
        } catch {
          break;
        }
      }
      queryClient.invalidateQueries({
        queryKey: ["research-session-graph", sessionId],
      });
    };
    window.addEventListener("online", flush);
    void flush();
    return () => window.removeEventListener("online", flush);
  }, [sessionId]);

  const startOnline = useMutation({
    mutationFn: async () =>
      record(
        dataOrThrow(
          await api.POST("/api/v1/local/literature-searches", {
            body: {
              query: onlineGoal.trim(),
              goal: "",
              area: "",
              target_count: 20,
              semantic_ranking: true,
              source_id: "",
            },
          }),
        ),
      ),
    onSuccess: (job) => {
      setOnlineJobId(text(job.job_id));
      setOnlineSearchId(text(record(job.checkpoint).search_id));
      setOnlineSelected([]);
    },
  });
  const acquireOnline = useMutation({
    mutationFn: async () => {
      await dataOrThrow(
        await api.PATCH(
          "/api/v1/local/literature-searches/{search_id}/selection",
          {
            params: { path: { search_id: onlineSearchId } },
            body: { work_ids: onlineSelected },
          },
        ),
      );
      return record(
        dataOrThrow(
          await api.POST(
            "/api/v1/local/literature-searches/{search_id}/acquisitions",
            {
              params: { path: { search_id: onlineSearchId } },
              body: {
                source_id: null,
                folder_name: onlineFolderName(onlineGoal),
                work_ids: onlineSelected,
              },
            },
          ),
        ),
      );
    },
    onSuccess: (job) => setOnlineAcquireJobId(text(job.job_id)),
  });
  useEffect(() => {
    if (text(record(onlineAcquireJob.data).state) !== "succeeded") return;
    setGoal(onlineGoal);
    const sourceId = text(
      record(record(onlineAcquireJob.data).checkpoint).source_id,
    );
    if (sourceId)
      setSelectedSources((current) => [...new Set([...current, sourceId])]);
    setOnlineOpen(false);
    queryClient.invalidateQueries({ queryKey: ["research-sources"] });
  }, [onlineAcquireJob.dataUpdatedAt]);

  const analyzeConnection = useMutation({
    mutationFn: async () =>
      record(
        dataOrThrow(
          await api.POST("/api/v1/principles/potential-relations", {
            body: { principle_ids: cart },
          }),
        ),
      ),
    onSuccess: async (value) => {
      if (sessionId)
        await dataOrThrow(
          await api.POST("/api/v1/research-sessions/{session_id}/artifacts", {
            params: { path: { session_id: sessionId } },
            body: { kind: "virtual_connection", payload: value },
          }),
        );
      queryClient.invalidateQueries({
        queryKey: ["research-artifacts", sessionId],
      });
      setStudioMessage(
        `${rows(value.items).length} virtual connections are now saved in this research session.`,
      );
    },
  });
  const derivePrinciples = useMutation({
    mutationFn: async () =>
      record(
        dataOrThrow(
          await api.POST("/api/v1/principles/virtual-principles/generate", {
            body: {
              principle_ids: cart,
              provider_profile_id: providerProfile,
              model,
              egress_confirmed: true,
              requested_count: 3,
              research_direction: researchDirection,
            },
          }),
        ),
      ),
    onSuccess: async (value) => {
      if (sessionId)
        await dataOrThrow(
          await api.POST("/api/v1/research-sessions/{session_id}/artifacts", {
            params: { path: { session_id: sessionId } },
            body: { kind: "virtual_principle", payload: value },
          }),
        );
      setGeneratedPrinciples(rows(value.items));
      setSavedVirtualIds({});
      queryClient.invalidateQueries({
        queryKey: ["research-artifacts", sessionId],
      });
      setStudioMessage(
        `${rows(value.items).length} virtual Principles are saved in this session tray.`,
      );
    },
  });
  const deleteArtifact = useMutation({
    mutationFn: async (artifactId: string) =>
      dataOrThrow(
        await api.DELETE(
          "/api/v1/research-sessions/{session_id}/artifacts/{artifact_id}",
          {
            params: {
              path: { session_id: sessionId, artifact_id: artifactId },
            },
          },
        ),
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["research-artifacts", sessionId],
      }),
  });
  const deleteVirtualPrinciple = useMutation({
    mutationFn: async ({
      virtualId,
      candidateId,
    }: {
      virtualId: string;
      candidateId: string;
    }) => {
      await saveChain.current.catch(() => undefined);
      return dataOrThrow(
        await api.DELETE(
          "/api/v1/research-sessions/{session_id}/virtual-principles/{virtual_id}",
          {
            params: {
              path: { session_id: sessionId, virtual_id: virtualId },
              query: { candidate_id: candidateId },
            },
          },
        ),
      );
    },
    onSuccess: (_, variables) => {
      if (selectedId === variables.candidateId) setSelectedId("");
      setVirtualDeleteTarget("");
      setGeneratedPrinciples((current) =>
        current.filter(
          (item, index) =>
            (text(item.virtual_id) || `virtual:${index}`) !== variables.virtualId,
        ),
      );
      setSavedVirtualIds((current) => {
        const next = { ...current };
        delete next[variables.virtualId];
        return next;
      });
      setActionNotice(
        "Virtual Principle deleted from this workspace, its graph, and the local virtual library.",
      );
      void queryClient.invalidateQueries({
        queryKey: ["research-artifacts", sessionId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["research-session-graph", sessionId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["local-virtual-principles"],
      });
    },
    onError: () => {
      setVirtualDeleteTarget("");
      setActionNotice(
        "This Virtual Principle could not be deleted yet. Nothing else was changed.",
      );
    },
  });
  const addSavedVirtualToGraph = async (
    item: UnknownRecord,
    candidateId: string,
    index: number,
  ) => {
    const proposal = record(item.proposal);
    const position = graphInsertionPosition(candidateId, index);
    const save = sendGraphOperations([
      {
        action: "add",
        principle_id: candidateId,
        origin: "virtual_principle",
        payload: {
          ...proposal,
          id: candidateId,
          principle_id: candidateId,
          title: proposal.title,
          claim: proposal.claim,
          area: proposal.area,
          principle_class: "literature",
          virtual: true,
        },
        ...position,
      },
    ]);
    setFocusTarget({ id: candidateId, request: Date.now() });
    await save;
    setActionNotice("Virtual Principle added back to the graph and centered.");
  };

  const saveVirtualLocally = async (item: UnknownRecord, index: number) => {
    const proposal = record(
      item.proposal,
    ) as components["schemas"]["VirtualPrincipleProposal"];
    const generation = record(
      artifactRows.find(
        (artifact) => text(artifact.kind) === "virtual_principle",
      )?.payload,
    );
    const saved = record(
      dataOrThrow(
        await api.POST("/api/v1/principles/virtual-principles/save", {
          body: {
            proposal,
            provider: text(generation.provider) || providerProfile,
            model: text(generation.model) || model,
            trace: record(generation.trace),
          },
        }),
      ),
    );
    const candidateId = text(saved.candidate_id);
    const virtualId = text(item.virtual_id) || `virtual:${index}`;
    setSavedVirtualIds((current) => ({ ...current, [virtualId]: candidateId }));
    void queryClient.invalidateQueries({ queryKey: ["local-virtual-principles"] });
    if (sessionId && candidateId) {
      await dataOrThrow(
        await api.POST("/api/v1/research-sessions/{session_id}/artifacts", {
          params: { path: { session_id: sessionId } },
          body: {
            kind: "virtual_principle",
            payload: {
              saved_receipt: true,
              provider: text(generation.provider) || providerProfile,
              model: text(generation.model) || model,
              trace: record(generation.trace),
              items: [{ ...item, candidate_id: candidateId }],
            },
          },
        }),
      );
      await queryClient.invalidateQueries({
        queryKey: ["research-artifacts", sessionId],
      });
    }
    if (candidateId) await addSavedVirtualToGraph(item, candidateId, index);
  };

  const activeRun = record(session.data?.active_run);
  const branches = Object.entries(record(activeRun.branches));
  const onlineRows = rows(onlineSearch.data?.results);
  const primaryError =
    session.error ??
    graph.error ??
    cloudAtlas.error ??
    sources.error ??
    createSession.error ??
    startAnotherRun.error ??
    saveProviderKey.error;

  useEffect(() => {
    if (
      !launchedGoalRef.current ||
      text(activeRun.goal).trim() !== launchedGoalRef.current
    )
      return;
    if (terminal.has(text(activeRun.state))) {
      setRunNotice(
        "New results are ready. Use Add or Remove to shape the current graph.",
      );
      launchedGoalRef.current = "";
      void queryClient.invalidateQueries({
        queryKey: ["research-results", sessionId],
      });
    }
  }, [sessionId, session.dataUpdatedAt]);

  useEffect(() => {
    if (
      !sessionId ||
      !activeRunId ||
      !terminal.has(activeRunState) ||
      hydratedResultsRunRef.current === activeRunId
    )
      return;
    hydratedResultsRunRef.current = activeRunId;
    void queryClient.invalidateQueries({
      queryKey: ["research-results", sessionId, activeRunId],
    });
    void queryClient.invalidateQueries({
      queryKey: ["research-session-graph", sessionId],
    });
  }, [sessionId, activeRunId, activeRunState]);

  return (
    <div
      className={`research-workspace ${sessionId ? "has-session" : "is-new"} ${trayHidden ? "tray-hidden" : ""} ${studio ? "studio-open" : ""}`}
    >
      <header
        className={`research-command-bar ${sessionId ? "compact" : "welcome"}`}
      >
        {!sessionId ? (
          <div className="research-command-intro">
            <span className="eyebrow">New research</span>
            <h1>
              The living Principles Cloud for Autonomous Scientific Discovery
            </h1>
            <p>
              From scientific works to reusable Principles. From Principles to
              solutions.
            </p>
          </div>
        ) : null}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (goal.trim().length < 8) return;
            if (selectedSources.length && !Boolean(profile.configured)) {
              requestProviderSetup();
              return;
            }
            sessionId ? startAnotherRun.mutate() : createSession.mutate();
          }}
        >
          <input
            autoFocus={!sessionId}
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="Your research goal"
            aria-label="Research goal"
          />
          <button
            className="primary"
            disabled={
              goal.trim().length < 8 ||
              createSession.isPending ||
              startAnotherRun.isPending ||
              Boolean(
                sessionId &&
                  activeRun.state &&
                  !terminal.has(text(activeRun.state)),
              )
            }
          >
            {createSession.isPending || startAnotherRun.isPending
              ? "Starting…"
              : sessionId
                ? "Search again"
                : "Explore"}
          </button>
        </form>
        <details className="research-input-options" ref={optionsRef}>
          <summary>
            Sources & model{" "}
            <span>
              {selectedSources.length
                ? `${selectedSources.length} local folder${selectedSources.length === 1 ? "" : "s"}`
                : "Global Cloud only"}
            </span>
          </summary>
          <div className="research-options-popover">
            <div className="research-option-actions">
              <button onClick={() => addFolders.mutate()}>
                Add local folders
              </button>
              <button
                onClick={() => {
                  setOnlineGoal(goal);
                  setOnlineOpen(true);
                }}
              >
                Find papers online
              </button>
            </div>
            <div className="research-source-chips">
              {sourceRows.map((source) => (
                <label key={source.source_id} title={source.display_name}>
                  <input
                    type="checkbox"
                    checked={selectedSources.includes(source.source_id)}
                    onChange={(event) =>
                      setSelectedSources((current) =>
                        event.target.checked
                          ? [...new Set([...current, source.source_id])]
                          : current.filter((id) => id !== source.source_id),
                      )
                    }
                  />
                  <span>
                    <strong>{source.display_name}</strong>
                    <small>{source.document_count} papers</small>
                  </span>
                  <button
                    type="button"
                    aria-label={`Disconnect ${source.display_name}`}
                    onClick={(event) => {
                      event.preventDefault();
                      disconnectFolder.mutate(source.source_id);
                    }}
                  >
                    ×
                  </button>
                </label>
              ))}
            </div>
            {selectedSources.length ? (
              <label className="egress-confirm">
                <input
                  type="checkbox"
                  checked={confirmEgress}
                  onChange={(event) => setConfirmEgress(event.target.checked)}
                />
                <span>
                  Use the selected LLM on these folders. Nothing is uploaded to
                  Global Cloud.
                </span>
              </label>
            ) : null}
            <label>
              <span>LLM provider</span>
              <select
                value={providerProfile}
                onChange={(event) => {
                  const providerId = event.target.value;
                  const provider = record(
                    providerRows.find(
                      (item) => providerIdentifier(item) === providerId,
                    ),
                  );
                  setProviderProfile(providerId);
                  setModel(
                    window.localStorage.getItem(`principia:model:${providerId}`) ||
                      text(provider.default_model) ||
                      strings(provider.models)[0] ||
                      "",
                  );
                }}
              >
                {providerRows.map((item) => {
                  const id = providerIdentifier(item);
                  return (
                    <option key={id} value={id}>
                      {text(item.label) || id}
                      {item.configured ? " · ready" : " · key needed"}
                    </option>
                  );
                })}
              </select>
            </label>
            <label>
              <span>Model</span>
              <input
                list="research-provider-models"
                value={model}
                onChange={(event) => setModel(event.target.value)}
              />
              <datalist id="research-provider-models">
                {strings(profile.models).map((modelId) => (
                  <option key={modelId} value={modelId} />
                ))}
              </datalist>
              <small>
                {profile.configured
                  ? "This provider is configured in the current working directory."
                  : "Add this provider key through API & models before local extraction."}
              </small>
            </label>
            {!profile.configured ? (
              <label>
                <span>Provider API key</span>
                <div className="inline-provider-key">
                  <input
                    type="password"
                    value={providerKey}
                    onChange={(event) => setProviderKey(event.target.value)}
                    placeholder="Stored locally, never in Cloud"
                    autoComplete="off"
                  />
                  <button
                    disabled={
                      providerKey.length < 8 || saveProviderKey.isPending
                    }
                    onClick={() => saveProviderKey.mutate()}
                  >
                    {saveProviderKey.isPending ? "Connecting…" : "Connect"}
                  </button>
                </div>
              </label>
            ) : null}
            {providerMessage ? (
              <p className="inline-success">{providerMessage}</p>
            ) : null}
          </div>
        </details>
        <CloudStatusControl
          status={cloud.data ?? {}}
          fetching={cloud.isFetching}
          refreshing={refreshCloud.isPending}
          onRefresh={() => refreshCloud.mutate()}
        />
      </header>

      {runNotice ? (
        <div
          className={`research-run-notice ${startAnotherRun.isPending ? "active" : ""}`}
          role="status"
          aria-live="polite"
        >
          {startAnotherRun.isPending ? (
            <span className="spinner" />
          ) : (
            <span aria-hidden="true">✓</span>
          )}
          <strong>{runNotice}</strong>
          {!startAnotherRun.isPending ? (
            <button
              aria-label="Dismiss search status"
              onClick={() => setRunNotice("")}
            >
              ×
            </button>
          ) : null}
        </div>
      ) : null}

      {sessionId &&
      branches.length &&
      text(activeRun.state) !== "succeeded" ? (
        <section className="research-live-strip" aria-live="polite">
          <strong>{text(activeRun.state) || "starting"}</strong>
          {branches.map(([name, value]) => (
            <span key={name}>
              <i className={text(record(value).state)} />
              {name.startsWith("local:")
                ? "Local extraction"
                : "Global retrieval"}
              : {text(record(value).stage) || text(record(value).state)}
            </span>
          ))}
        </section>
      ) : null}

      {sessionId && !trayHidden ? (
        <aside className="research-result-tray">
          <header>
            <div>
              <strong>Research results</strong>
              <small>Choose what appears on the map</small>
            </div>
            <button
              className="research-tray-hide"
              aria-label="Hide results"
              onClick={() => setTrayHidden(true)}
            >
              <span>Hide</span>
              <b>‹</b>
            </button>
          </header>
          <nav>
            {(["global", "local", "meta"] as Tray[]).map((value) => (
              <button
                key={value}
                className={tray === value ? "selected" : ""}
                onClick={() => setTray(value)}
              >
                {value === "meta" ? "Foundations" : value}
              </button>
            ))}
          </nav>
          <div className="research-tray-list">
            {trayItems.map((item) => {
              const id =
                text(item.id) ||
                text(item.principle_id) ||
                text(item.candidate_id);
              const present = graphIds.has(id);
              return (
                <article
                  key={id}
                  className={
                    text(item.principle_class) === "meta" ? "meta" : ""
                  }
                >
                  <button
                    className="tray-preview"
                    onClick={() => {
                      setSelectedEdge(null);
                      setSelectedId(id);
                    }}
                  >
                    <small>
                      {text(item.principle_class) === "meta"
                        ? "◇ Meta-Principle"
                        : tray}
                    </small>
                    <strong>{itemTitle(item)}</strong>
                    <p>{text(item.claim)}</p>
                  </button>
                  <button
                    className={present ? "remove" : "add"}
                    onClick={async () => {
                      setActionNotice(
                        present
                          ? "Removing the Principle from this graph…"
                          : "Adding the Principle to this graph…",
                      );
                      try {
                        const position = graphInsertionPosition(id);
                        const save = sendGraphOperations([
                          {
                            action: present ? "remove" : "add",
                            principle_id: id,
                            payload: item,
                            origin: `tray:${tray}`,
                            ...position,
                          },
                        ]);
                        if (present) setSelectedId("");
                        else {
                          setFocusTarget({ id, request: Date.now() });
                        }
                        await save;
                        setActionNotice(
                          present
                            ? "Principle removed from this graph. It remains available in Results."
                            : "Principle added to this graph.",
                        );
                      } catch {
                        setActionNotice(
                          "The change is safely queued and will retry when the workspace reconnects.",
                        );
                      }
                    }}
                  >
                    {present ? "Remove" : "Add"}
                  </button>
                </article>
              );
            })}
            {!trayItems.length ? (
              <p className="tray-empty">
                {terminal.has(text(activeRun.state))
                  ? "No results in this section."
                  : "Results will appear here while the branches run."}
              </p>
            ) : null}
          </div>
        </aside>
      ) : sessionId ? (
        <button
          className="show-result-tray"
          onClick={() => setTrayHidden(false)}
        >
          Results <span>{Number(trayPage.data?.total ?? 0)}</span>
        </button>
      ) : null}

      <main className="research-canvas">
        <p className="sr-only" role="status" aria-live="polite">
          {mapFocusAnnouncement}
        </p>
        <div className="research-graph-navigation-tools">
          {mapSearchableCount ? (
            <details
              className="research-map-finder"
              ref={mapFinderRef}
              onToggle={(event) => {
                const details = event.currentTarget;
                if (details.open) {
                  if (edgeLayersRef.current) edgeLayersRef.current.open = false;
                  window.requestAnimationFrame(() =>
                    details.querySelector("input")?.focus(),
                  );
                }
              }}
            >
              <summary>
                <span aria-hidden="true">⌕</span>
                Find in map
              </summary>
              <div className="research-map-finder-popover">
                <header>
                  <div>
                    <small>Current map</small>
                    <strong>Find and focus a Principle</strong>
                  </div>
                  <span>{mapSearchableCount}</span>
                </header>
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    const first = mapSearchResults[0];
                    if (first)
                      focusGraphItem(first.item.principle_id, first.title);
                  }}
                >
                  <input
                    value={mapQuery}
                    onChange={(event) => setMapQuery(event.target.value)}
                    placeholder={
                      mapClaimCoverage
                        ? "Title, claim, area, or Principle ID"
                        : mapTitleCoverage
                          ? "Title, area, or Principle ID"
                          : "Area or Principle ID · zoom in for titles"
                    }
                    aria-label="Find a Principle in the current map"
                  />
                  <button
                    type="submit"
                    disabled={!mapSearchResults.length}
                    aria-label="Focus the first matching Principle"
                    title="Focus first match"
                  >
                    ↵
                  </button>
                </form>
                <div className="research-map-search-results" aria-live="polite">
                  {mapQuery.trim() ? (
                    mapSearchResults.length ? (
                      mapSearchResults.map((result) => (
                        <button
                          type="button"
                          key={result.item.principle_id}
                          onClick={() =>
                            focusGraphItem(
                              result.item.principle_id,
                              result.title,
                            )
                          }
                        >
                          <span>
                            {result.item.record_kind === "meta_principle"
                              ? "◇ Meta-Principle"
                              : result.area.replaceAll("-", " ") ||
                                "Literature Principle"}
                          </span>
                          <strong>
                            <ScientificText value={result.title} />
                          </strong>
                        </button>
                      ))
                    ) : (
                      <p>
                        No match in the fields loaded at this zoom.
                        {!mapSearchCoverageComplete
                          ? " Zoom in to load more titles and claims."
                          : ""}
                      </p>
                    )
                  ) : (
                    <p>
                      {mapSearchCoverageComplete
                        ? "Search every node loaded in this map."
                        : `Search fields loaded at this zoom: ${mapTitleCoverage}/${mapSearchableCount} titles and ${mapClaimCoverage}/${mapSearchableCount} claims. Zoom in for richer text.`}
                    </p>
                  )}
                </div>
              </div>
            </details>
          ) : null}
          {graphRows.length ? (
            <details
              className="research-edge-layers"
              ref={edgeLayersRef}
              onToggle={(event) => {
                if (event.currentTarget.open && mapFinderRef.current)
                  mapFinderRef.current.open = false;
              }}
            >
              <summary>
                <span aria-hidden="true">≋</span>
                Layers
                <b>
                  {
                    EDGE_LAYER_OPTIONS.filter(
                      (option) =>
                        (sessionId || option.id !== "virtual") &&
                        visibleEdgeLayers[option.id],
                    ).length
                  }
                  /{sessionId ? 3 : 2}
                </b>
              </summary>
              <div className="research-edge-layer-popover">
                <header>
                  <small>Relationship visibility</small>
                  <strong>Separate evidence from visual context</strong>
                </header>
                {EDGE_LAYER_OPTIONS.filter(
                  (option) => sessionId || option.id !== "virtual",
                ).map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    className={visibleEdgeLayers[option.id] ? "active" : ""}
                    aria-pressed={visibleEdgeLayers[option.id]}
                    onClick={() => toggleEdgeLayer(option.id)}
                  >
                    <i className={`edge ${option.id}`} aria-hidden="true" />
                    <span>
                      <strong>{option.label}</strong>
                      <small>{option.title}</small>
                    </span>
                    <b>{visibleEdgeLayers[option.id] ? "On" : "Off"}</b>
                  </button>
                ))}
              </div>
            </details>
          ) : null}
        </div>
        <div className="research-graph-tools">
          {sessionId ? (
            <>
              <button
                onClick={() => {
                  setStudio("");
                  closeArtifactDrawer();
                  setGlobalFinderOpen(true);
                }}
              >
                ＋ Add Principle
              </button>
              <button
                onClick={() => {
                  setGlobalFinderOpen(false);
                  closeArtifactDrawer();
                  setTrayHidden(true);
                  setStudio("connection");
                  setCart([]);
                  setStudioMessage("");
                }}
              >
                Derive connection
              </button>
              <button
                onClick={() => {
                  setGlobalFinderOpen(false);
                  closeArtifactDrawer();
                  setTrayHidden(true);
                  setStudio("principle");
                  setCart([]);
                  setStudioMessage("");
                }}
              >
                Derive Principles
              </button>
              <button
                onClick={() =>
                  sendGraphOperations([
                    {
                      action: "theme",
                      theme:
                        sessionTheme === "daylight" ? "deep-space" : "daylight",
                    },
                  ])
                }
              >
                {sessionTheme === "daylight" ? "Starlight" : "Deep space"}
              </button>
            </>
          ) : (
            <span>
              Explore Literature and Meta-Principles together, or enter a
              question above.
            </span>
          )}
        </div>
        {!sessionId && atlasAreas.length ? (
          <details className="research-area-filter" ref={areaFilterRef}>
            <summary>
              <span>Areas</span>
              <strong>
                {selectedAtlasAreas.length
                  ? `${selectedAtlasAreas.length} selected`
                  : "All scientific fields"}
              </strong>
              <b aria-hidden="true">⌄</b>
            </summary>
            <div className="research-area-filter-popover">
              <header>
                <div>
                  <small>Filter the living map</small>
                  <strong>Scientific areas</strong>
                </div>
                {selectedAtlasAreas.length ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedAtlasAreas([]);
                      setAtlasViewport(INITIAL_ATLAS_VIEWPORT);
                      setSelectedId("");
                    }}
                  >
                    Show all
                  </button>
                ) : null}
              </header>
              <div className="research-area-options">
                {atlasAreas.map((area) => {
                  const value = text(area.area);
                  const checked = selectedAtlasAreas.includes(value);
                  return (
                    <label key={value} className={checked ? "selected" : ""}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleAtlasArea(value)}
                      />
                      <span>
                        <strong>{text(area.display_name) || value}</strong>
                        <small>
                          {Number(area.principle_count ?? 0).toLocaleString()} Principles
                          {Number(area.meta_count ?? 0)
                            ? ` · ${Number(area.meta_count).toLocaleString()} Meta`
                            : ""}
                        </small>
                      </span>
                    </label>
                  );
                })}
              </div>
              <p>
                Select one or several areas. The map keeps both Literature and
                Meta-Principles from those fields.
              </p>
            </div>
          </details>
        ) : null}
        {graphRows.length ? (
          <ResearchGraph
            key={
              sessionId ||
              `global-cloud-atlas:${selectedAtlasAreas.join("|") || "all"}`
            }
            items={graphRows}
            edges={
              sessionId ? rows(graph.data?.edges) : rows(cloudAtlas.data?.edges)
            }
            virtualEdges={virtualEdges}
            selectedId={selectedId}
            theme={sessionTheme}
            deferViewportUntilInteraction={!sessionId}
            initialViewport={
              sessionId
                ? {
                    x: Number(persistedViewport.x ?? 0.5),
                    y: Number(persistedViewport.y ?? 0.5),
                    angle: Number(persistedViewport.angle ?? 0),
                    ratio: Number(persistedViewport.ratio ?? 3),
                  }
                : undefined
            }
            focusTarget={focusTarget}
            visibleEdgeLayers={visibleEdgeLayers}
            onSelect={(id) => {
              setSelectedEdge(null);
              setSelectedId(id);
            }}
            onSelectEdge={(edge) => {
              setSelectedId("");
              setSelectedEdge(edge);
            }}
            onStageClick={() => {
              if (studio) setStudio("");
              if (artifactDrawer) closeArtifactDrawer();
            }}
            onMove={(moves) =>
              sendGraphOperations(
                moves.map((move) => ({ action: "move", ...move })),
              )
            }
            onViewport={settleViewport}
          />
        ) : (
          <div className="research-graph-empty">
            <span className="spinner" />
            <strong>Opening the Principles map…</strong>
          </div>
        )}
        <div className="research-map-legend" aria-label="Map legend">
          <span>
            <i className="ordinary" />
            Literature Principles
          </span>
          <span>
            <i className="meta" />
            Meta foundations
          </span>
          {sessionId ? (
            <span>
              <i className="virtual" />
              Virtual hypotheses
            </span>
          ) : null}
          <small>Two-finger move · pinch to zoom</small>
        </div>
        {selected ? (
          <aside
            className={`research-inspector ${selected.record_kind === "meta_principle" ? "meta" : ""}`}
            ref={inspectorRef}
            tabIndex={-1}
            aria-labelledby="research-principle-inspector-title"
            style={{
              transform: `translate3d(${inspectorOffset.x}px, ${inspectorOffset.y}px, 0)`,
              ...(inspectorSize
                ? {
                    width: `${inspectorSize.width}px`,
                    height: `${inspectorSize.height}px`,
                  }
                : {}),
            }}
          >
            <button
              type="button"
              className="inspector-drag-rail"
              onPointerDown={beginInspectorDrag}
              aria-label="Drag Principle details panel"
              title="Drag from this edge"
            >
              <span />
            </button>
            <button
              type="button"
              className="inspector-drag-side left"
              onPointerDown={beginInspectorDrag}
              aria-label="Drag Principle details panel from the left edge"
              title="Drag to move"
            >
              <span />
            </button>
            <button
              type="button"
              className="inspector-drag-side right"
              onPointerDown={beginInspectorDrag}
              aria-label="Drag Principle details panel from the right edge"
              title="Drag to move"
            >
              <span />
            </button>
            <button
              type="button"
              className="inspector-resize-handle"
              onPointerDown={beginInspectorResize}
              aria-label="Resize Principle details panel"
              title="Drag to resize"
            />
            <div className="inspector-scroll-region">
            <header
              className="inspector-heading"
            >
              <div>
                <small>
                  {selected.record_kind === "meta_principle"
                    ? "◇ Foundational Meta-Principle"
                    : text(selected.payload.area).replaceAll("-", " ")}
                </small>
                <h2 id="research-principle-inspector-title">
                  <ScientificText value={itemTitle(selected.payload)} />
                </h2>
              </div>
              <button
                className="close"
                aria-label="Close details"
                onClick={() => setSelectedId("")}
              >
                ×
              </button>
            </header>
            <div
              className="principle-metrics"
              title="Reliability reflects review, maturity, evidence, boundary, and falsifiability. Influence reflects this snapshot's evidence and graph connectivity."
            >
              <span>
                <b>{reliabilityScore(selected.payload)}</b> Reliability
              </span>
              <span>
                <b>{influenceScore(selected.payload)}</b> Influence
              </span>
            </div>
            {selected.record_kind === "meta_principle" ? (
              <div className="foundation-signature">
                <span>
                  Maturity{" "}
                  <b>{text(selected.payload.maturity) || "reviewed"}</b>
                </span>
                <span>
                  Stability{" "}
                  <b>{text(selected.payload.stability) || "not stated"}</b>
                </span>
              </div>
            ) : null}
            <dl>
              {selectedArgumentForDisplay ? (
                <div>
                  <dt>Argument</dt>
                  <dd><ScientificText value={selectedArgumentForDisplay} /></dd>
                </div>
              ) : null}
              {selectedInterpretation ? (
                <div>
                  <dt>Interpretation</dt>
                  <dd><ScientificText value={selectedInterpretation} /></dd>
                </div>
              ) : null}
              <div>
                <dt>Conditions</dt>
                <dd>
                  <ScientificText
                    value={
                      strings(selected.payload.conditions).join(" · ") ||
                      "No additional condition recorded"
                    }
                  />
                </dd>
              </div>
              <div>
                <dt>Boundary & disproof</dt>
                <dd>
                  <ScientificText
                    value={
                      strings(selected.payload.boundary).join(" · ") ||
                      text(selected.payload.falsifier) ||
                      "Not recorded"
                    }
                  />
                </dd>
              </div>
              <div>
                <dt>Applications</dt>
                <dd>
                  <ScientificText
                    value={
                      strings(selected.payload.applications).join(" · ") ||
                      "Not recorded"
                    }
                  />
                </dd>
              </div>
            </dl>
            {relatedMetaPrinciples.length ? (
              <div className="inspector-foundation">
                <strong>Related Meta-Principles</strong>
                {text(record(selected.payload.foundation_assessment).verdict) ===
                  "grounded" &&
                text(record(selected.payload.foundation_assessment).rationale) ? (
                  <p>
                    <ScientificText
                      value={text(
                        record(selected.payload.foundation_assessment).rationale,
                      )}
                    />
                  </p>
                ) : null}
                {relatedMetaPrinciples.map((foundation) => (
                    <button
                      key={foundation.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        void openFoundation(foundation.id, foundation.meta);
                      }}
                    >
                      <span>
                        {foundation.relationType.replaceAll("_", " ")}
                        {foundation.reviewed ? " · reviewed" : " · map context"}
                      </span>
                      <strong>
                        <ScientificText value={itemTitle(foundation.meta)} />
                      </strong>
                    </button>
                  ))}
              </div>
            ) : null}
            {selectedSourcesForDisplay.length ? (
              <div className="inspector-sources">
                <strong>Public sources</strong>
                {selectedSourcesForDisplay.map((source) => {
                    const sourceUrl =
                      text(source.source_url) ||
                      text(source.landing_url) ||
                      strings(source.source_urls)[0] ||
                      text(record(source.availability).full_text_url);
                    return sourceUrl ? (
                      <a
                        key={text(source.work_id) || sourceUrl}
                        href={sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {text(source.title) || sourceUrl}
                      </a>
                    ) : (
                      <span key={text(source.work_id) || itemTitle(source)}>
                        {text(source.title) ||
                          "Source metadata available; public URL unresolved"}
                      </span>
                    );
                  },
                )}
              </div>
            ) : null}
            <div className="inspector-actions">
              {studio ? (
                <button
                  className="primary"
                  disabled={
                    cart.includes(selected.principle_id) || cart.length >= 20
                  }
                  onClick={() =>
                    setCart((current) => [...current, selected.principle_id])
                  }
                >
                  {cart.includes(selected.principle_id)
                    ? "Already selected"
                    : "Add to derivation"}
                </button>
              ) : null}
              {sessionId && graphIds.has(selected.principle_id) ? (
                <button
                  className="remove-from-graph"
                  onClick={async () => {
                    await sendGraphOperations([
                      { action: "remove", principle_id: selected.principle_id },
                    ]);
                    setSelectedId("");
                    setActionNotice(
                      "Principle removed from this graph. The underlying record remains available.",
                    );
                  }}
                >
                  Remove from graph
                </button>
              ) : null}
            </div>
            </div>
          </aside>
        ) : null}
        {selectedEdge ? (
          <aside
            className={`research-inspector edge ${selectedEdgeLayer ?? ""}`}
            ref={inspectorRef}
            tabIndex={-1}
            aria-labelledby="research-edge-inspector-title"
            style={{
              transform: `translate3d(${inspectorOffset.x}px, ${inspectorOffset.y}px, 0)`,
              ...(inspectorSize
                ? {
                    width: `${inspectorSize.width}px`,
                    height: `${inspectorSize.height}px`,
                  }
                : {}),
            }}
          >
            <button
              type="button"
              className="inspector-drag-rail"
              onPointerDown={beginInspectorDrag}
              aria-label="Drag connection details panel"
              title="Drag from this edge"
            >
              <span />
            </button>
            <button
              type="button"
              className="inspector-drag-side left"
              onPointerDown={beginInspectorDrag}
              aria-label="Drag connection details panel from the left edge"
              title="Drag to move"
            >
              <span />
            </button>
            <button
              type="button"
              className="inspector-drag-side right"
              onPointerDown={beginInspectorDrag}
              aria-label="Drag connection details panel from the right edge"
              title="Drag to move"
            >
              <span />
            </button>
            <button
              type="button"
              className="inspector-resize-handle"
              onPointerDown={beginInspectorResize}
              aria-label="Resize connection details panel"
              title="Drag to resize"
            />
            <div className="inspector-scroll-region">
            <header
              className="inspector-heading"
            >
              <div>
                <small>
                  {selectedEdgeLayer === "scientific"
                    ? "Cloud relation"
                    : selectedEdgeLayer === "virtual"
                      ? "Virtual connection · unreviewed"
                      : "Map context · navigation only"}
                </small>
                <h2 id="research-edge-inspector-title">
                  {selectedEdge.relation_type.replaceAll("_", " ")}
                </h2>
              </div>
              <button
                className="close"
                aria-label="Close connection details"
                onClick={() => setSelectedEdge(null)}
              >
                ×
              </button>
            </header>
            <p className="claim">
              <ScientificText value={selectedEdge.rationale} />
            </p>
            {selectedEdge.confidence !== undefined ? (
              <div className="edge-confidence">
                <span>Confidence</span>
                <strong>
                  {Math.round(
                    selectedEdge.confidence <= 1
                      ? selectedEdge.confidence * 100
                      : selectedEdge.confidence,
                  )}
                  %
                </strong>
              </div>
            ) : null}
            <div className="edge-endpoints">
              <strong>Connects</strong>
              <button
                onPointerDown={(event) => {
                  event.stopPropagation();
                  event.preventDefault();
                  const id = selectedEdge.source_id;
                  setSelectedEdge(null);
                  closeArtifactDrawer();
                  setSelectedId(id);
                  setFocusTarget({ id, request: Date.now() });
                  setActionNotice("Opening the connected Principle…");
                }}
              >
                <small>Source</small>
                <span>
                  <ScientificText
                    value={
                      edgeSource
                        ? itemTitle(edgeSource.payload)
                        : selectedEdge.source_id
                    }
                  />
                </span>
              </button>
              <button
                onPointerDown={(event) => {
                  event.stopPropagation();
                  event.preventDefault();
                  const id = selectedEdge.target_id;
                  setSelectedEdge(null);
                  closeArtifactDrawer();
                  setSelectedId(id);
                  setFocusTarget({ id, request: Date.now() });
                  setActionNotice("Opening the connected Principle…");
                }}
              >
                <small>Target</small>
                <span>
                  <ScientificText
                    value={
                      edgeTarget
                        ? itemTitle(edgeTarget.payload)
                        : selectedEdge.target_id
                    }
                  />
                </span>
              </button>
            </div>
            {selectedEdgeLayer === "context" ? (
              <p className="edge-context-note">
                This edge organizes the map or exposes non-validating context.
                It is not evidence that either Principle supports the other.
              </p>
            ) : selectedEdgeLayer === "virtual" ? (
              <p className="edge-context-note virtual">
                This relationship was derived in the current session and has
                not been reviewed as a scientific relation.
              </p>
            ) : null}
            </div>
          </aside>
        ) : null}
      </main>

      {globalFinderOpen ? (
        <div
          className="research-modal-backdrop"
          onPointerDown={(event) => {
            if (event.target === event.currentTarget)
              setGlobalFinderOpen(false);
          }}
        >
          <aside className="research-modal">
            <header>
              <div>
                <small>Semantic Cloud search</small>
                <h2>Add Global Principles</h2>
              </div>
              <button
                aria-label="Close"
                onClick={() => setGlobalFinderOpen(false)}
              >
                ×
              </button>
            </header>
            <form
              className="global-principle-search"
              onSubmit={(event) => {
                event.preventDefault();
                submitGlobalFinderSearch();
              }}
            >
              <input
                autoFocus
                value={globalQuery}
                onChange={(event) => setGlobalQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    submitGlobalFinderSearch();
                  }
                }}
                placeholder="Search mechanisms, applications, or scientific questions"
              />
              <button
                className="primary"
                disabled={globalFinder.isFetching}
              >
                {globalFinder.isFetching ? "Searching…" : "Search"}
              </button>
            </form>
            <div className="global-principle-search-state" aria-live="polite">
              {globalFinder.isFetching ? (
                <p><span className="spinner" /> Searching the Global Cloud semantically…</p>
              ) : globalFinder.error ? (
                <ErrorState error={globalFinder.error} retry={() => void globalFinder.refetch()} />
              ) : globalSearchQuery && !rows(globalFinder.data?.items).length ? (
                <p>No matching Principles were found. Try a broader scientific mechanism or application.</p>
              ) : globalSearchQuery ? (
                <p>{Number(globalFinder.data?.total ?? rows(globalFinder.data?.items).length).toLocaleString()} related Cloud records found.</p>
              ) : (
                <p>Press Enter or Search to retrieve related Literature and Meta-Principles.</p>
              )}
              {globalFinderMessage ? <p className="field-error">{globalFinderMessage}</p> : null}
            </div>
            <div>
              {rows(globalFinder.data?.items)
                .filter(
                  (item) =>
                    ["principle", "meta_principle"].includes(
                      text(item.entity),
                    ) || text(item.principle_class),
                )
                .map((item) => {
                  const id = text(item.id) || text(item.principle_id);
                  const present = graphIds.has(id);
                  return (
                    <article
                      key={id}
                      className={
                        text(item.principle_class) === "meta" ? "meta" : ""
                      }
                    >
                      <button
                        onClick={() => {
                          setSelectedEdge(null);
                          setSelectedId(id);
                          setGlobalFinderOpen(false);
                        }}
                      >
                        <small>
                          {text(item.principle_class) === "meta"
                            ? "◇ Meta-Principle"
                            : "Global Principle"}
                        </small>
                        <strong>{itemTitle(item)}</strong>
                        <p>{text(item.claim)}</p>
                      </button>
                      <button
                        onClick={() => void addOrRevealPrinciple(item, present)}
                      >
                        {present ? "Show on graph" : "Add to graph"}
                      </button>
                    </article>
                  );
                })}
            </div>
          </aside>
        </div>
      ) : null}

      {studio ? (
        <aside className="derivation-studio">
          <header>
            <div>
              <small>
                {studio === "connection"
                  ? "Relationship synthesis"
                  : "Multi-level reasoning"}
              </small>
              <h2>
                {studio === "connection"
                  ? "Derive virtual connections"
                  : "Derive virtual Principles"}
              </h2>
            </div>
            <button
              className="studio-close"
              aria-label="Close derivation studio"
              onClick={() => setStudio("")}
            >
              ×
            </button>
          </header>
          <p>
            Select 2–20 Principles. Click any selected item to inspect it
            without covering this studio.
          </p>
          <input
            value={cartSearch}
            onChange={(event) => setCartSearch(event.target.value)}
            placeholder="Search results to add"
          />
          <div className="derivation-search-results">
            {principleCatalog
              .filter((item) =>
                `${itemTitle(item)} ${text(item.claim)}`
                  .toLowerCase()
                  .includes(cartSearch.toLowerCase()),
              )
              .slice(0, 20)
              .map((item) => {
                const id =
                  text(item.id) ||
                  text(item.principle_id) ||
                  text(item.candidate_id);
                return (
                  <article
                    key={id}
                    className={
                      text(item.principle_class) === "meta" ? "meta" : ""
                    }
                  >
                    <button
                      className="derivation-preview"
                      onClick={() => {
                        setSelectedEdge(null);
                        setSelectedId(id);
                      }}
                    >
                      <small>
                        {text(item.principle_class) === "meta"
                          ? "Meta foundation"
                          : "Principle"}
                      </small>
                      <span>{itemTitle(item)}</span>
                    </button>
                    <button
                      className="derivation-add"
                      aria-label={`Add ${itemTitle(item)} to selection`}
                      disabled={cart.includes(id) || cart.length >= 20}
                      onClick={() => setCart((current) => [...current, id])}
                    >
                      ＋
                    </button>
                  </article>
                );
              })}
          </div>
          <div className="derivation-cart">
            <strong>Selected · {cart.length}/20</strong>
            {cart.map((id) => {
              const item = principleCatalog.find(
                (candidate) =>
                  (text(candidate.id) ||
                    text(candidate.principle_id) ||
                    text(candidate.candidate_id)) === id,
              );
              return (
                <button key={id} onClick={() => setSelectedId(id)}>
                  <span>{item ? itemTitle(item) : id}</span>
                  <b
                    onClick={(event) => {
                      event.stopPropagation();
                      setCart((current) =>
                        current.filter((value) => value !== id),
                      );
                    }}
                  >
                    ×
                  </b>
                </button>
              );
            })}
          </div>
          {studio === "principle" ? (
            <textarea
              value={researchDirection}
              onChange={(event) => setResearchDirection(event.target.value)}
              placeholder="Optional direction or constraint"
            />
          ) : null}
          <button
            className="primary full"
            disabled={analyzeConnection.isPending || derivePrinciples.isPending}
            onClick={() => {
              if (cart.length < 2) {
                setStudioMessage(
                  "Select at least two Principles before starting the derivation.",
                );
                return;
              }
              if (studio === "principle" && !Boolean(profile.configured)) {
                requestProviderSetup();
                return;
              }
              setStudioMessage("");
              studio === "connection"
                ? analyzeConnection.mutate()
                : derivePrinciples.mutate();
            }}
          >
            {analyzeConnection.isPending || derivePrinciples.isPending
              ? "Reading claims → mapping mechanisms → testing boundaries → balancing reliability and novelty…"
              : studio === "connection"
                ? "Derive connections"
                : "Derive virtual Principles"}
          </button>
          {studio === "principle" && !Boolean(profile.configured) ? (
            <div className="provider-required-callout" role="note">
              <div>
                <strong>Connect {text(profile.label) || providerProfile}</strong>
                <span>
                  Virtual Principles require an LLM. Your API key stays only in
                  this working directory.
                </span>
              </div>
              <button onClick={requestProviderSetup}>Add API key</button>
            </div>
          ) : null}
          {analyzeConnection.isPending || derivePrinciples.isPending ? (
            <div className="derivation-progress" aria-live="polite">
              <span className="active">Reading evidence</span>
              <span>Mapping mechanisms</span>
              <span>Challenging boundaries</span>
              <span>Balancing novelty</span>
            </div>
          ) : null}
          {studioMessage ? (
            <p className="inline-success">{studioMessage}</p>
          ) : null}
          {analyzeConnection.error || derivePrinciples.error ? (
            <ErrorState
              error={analyzeConnection.error ?? derivePrinciples.error}
            />
          ) : null}
          {generatedPrinciples.map((item, index) => {
            const proposal = record(item.proposal);
            const virtualId = text(item.virtual_id) || `virtual:${index}`;
            const candidateId = savedVirtualCandidates[virtualId] || "";
            const present = Boolean(candidateId && graphIds.has(candidateId));
            return (
              <article
                className="generated-virtual-principle"
                key={text(item.virtual_id) || index}
              >
                <small>Virtual hypothesis</small>
                <strong>{itemTitle(proposal)}</strong>
                <p>{text(proposal.claim)}</p>
                <button
                  disabled={present}
                  onClick={() =>
                    void (candidateId
                      ? addSavedVirtualToGraph(item, candidateId, index)
                      : saveVirtualLocally(item, index))
                  }
                >
                  {present
                    ? "Saved locally and added"
                    : candidateId
                      ? "Add back to graph"
                      : "Save locally & add to graph"}
                </button>
              </article>
            );
          })}
        </aside>
      ) : null}

      {sessionId && artifactRows.length ? (
        <div className="artifact-tray-launchers">
          <button
            onClick={() => {
              const next =
                artifactDrawer === "virtual_connection"
                  ? ""
                  : "virtual_connection";
              setSelectedId("");
              setSelectedEdge(null);
              setStudio("");
              setGlobalFinderOpen(false);
              setVirtualDeleteTarget("");
              setArtifactDrawer(next);
            }}
          >
            Connections{" "}
            <b>
              {
                virtualConnectionItems.length
              }
            </b>
          </button>
          <button
            onClick={() => {
              const next =
                artifactDrawer === "virtual_principle"
                  ? ""
                  : "virtual_principle";
              setSelectedId("");
              setSelectedEdge(null);
              setStudio("");
              setGlobalFinderOpen(false);
              setVirtualDeleteTarget("");
              setArtifactDrawer(next);
            }}
          >
            Virtual Principles{" "}
            <b>
              {
                virtualPrincipleItems.length
              }
            </b>
          </button>
        </div>
      ) : null}
      {artifactDrawer ? (
        <>
          <button
            className="research-drawer-scrim"
            aria-label="Close saved artifacts"
            onClick={closeArtifactDrawer}
          />
          <aside className="artifact-drawer">
            <header>
              <strong>
                {artifactDrawer === "virtual_connection"
                  ? "Virtual connections"
                  : "Virtual Principles"}
              </strong>
              <button
                aria-label="Close saved artifacts"
                onClick={closeArtifactDrawer}
              >
                ×
              </button>
            </header>
            {artifactDrawer === "virtual_principle"
              ? virtualPrincipleItems.map((item, index) => {
                  const proposal = record(item.proposal);
                  const virtualId = text(item.virtual_id) || `virtual:${index}`;
                  const candidateId = savedVirtualCandidates[virtualId] || "";
                  const present = Boolean(candidateId && graphIds.has(candidateId));
                  return (
                    <article className="artifact-record" key={virtualId}>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          if (candidateId) {
                            closeArtifactDrawer();
                            setSelectedEdge(null);
                            setSelectedId(candidateId);
                            if (present)
                              setFocusTarget({ id: candidateId, request: Date.now() });
                          }
                        }}
                      >
                        <small>Virtual hypothesis</small>
                        <strong><ScientificText value={itemTitle(proposal)} /></strong>
                        <span><ScientificText value={text(proposal.claim)} /></span>
                      </button>
                      <div className="artifact-record-actions">
                        {virtualDeleteTarget === virtualId ? (
                          <>
                            <small>Delete permanently?</small>
                            <button
                              onClick={() => setVirtualDeleteTarget("")}
                            >
                              Cancel
                            </button>
                            <button
                              className="danger"
                              disabled={deleteVirtualPrinciple.isPending}
                              onClick={() =>
                                deleteVirtualPrinciple.mutate({
                                  virtualId,
                                  candidateId,
                                })
                              }
                            >
                              {deleteVirtualPrinciple.isPending
                                ? "Deleting…"
                                : "Delete"}
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              disabled={present}
                              onClick={() =>
                                void (candidateId
                                  ? addSavedVirtualToGraph(item, candidateId, index)
                                  : saveVirtualLocally(item, index))
                              }
                            >
                              {present
                                ? "On graph"
                                : candidateId
                                  ? "Add back"
                                  : "Save & add"}
                            </button>
                            <button
                              className="delete-virtual"
                              onClick={() => setVirtualDeleteTarget(virtualId)}
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </div>
                    </article>
                  );
                })
              : artifactRows
                  .filter(
                    (artifact) => text(artifact.kind) === "virtual_connection",
                  )
                  .map((artifact) => (
                    <article className="artifact-batch" key={text(artifact.artifact_id)}>
                      <div>
                        <strong>
                          {rows(record(artifact.payload).items).length} connections
                        </strong>
                        {rows(record(artifact.payload).items).map((connection) => (
                          <button
                            key={text(connection.relation_id)}
                            onClick={(event) => {
                              event.stopPropagation();
                              setSelectedId("");
                              closeArtifactDrawer();
                              setSelectedEdge({
                                edge_id: text(connection.relation_id),
                                source_id:
                                  text(connection.source) ||
                                  text(connection.source_principle_id),
                                target_id:
                                  text(connection.target) ||
                                  text(connection.target_principle_id),
                                edge_class: "virtual",
                                relation_type:
                                  text(connection.relation_type) ||
                                  "derived connection",
                                rationale:
                                  text(connection.rationale) ||
                                  "Derived in this research session.",
                                confidence: Number.isFinite(
                                  Number(connection.confidence),
                                )
                                  ? Number(connection.confidence)
                                  : undefined,
                              });
                            }}
                          >
                            {(
                              text(connection.relation_type) ||
                              "derived connection"
                            ).replaceAll("_", " ")}
                          </button>
                        ))}
                      </div>
                      <button
                        aria-label="Delete connection batch"
                        onClick={() =>
                          deleteArtifact.mutate(text(artifact.artifact_id))
                        }
                      >
                        ×
                      </button>
                    </article>
                  ))}
          </aside>
        </>
      ) : null}

      {onlineOpen ? (
        <div
          className="research-modal-backdrop"
          onPointerDown={(event) => {
            if (event.target === event.currentTarget) setOnlineOpen(false);
          }}
        >
          <aside className="online-research-modal">
            <header>
              <div>
                <small>Build a managed local dataset</small>
                <h2>Find papers online</h2>
                <p>
                  Papers are saved under{" "}
                  <code>local_data/{onlineFolderName(onlineGoal)}</code>.
                </p>
              </div>
              <button aria-label="Close" onClick={() => setOnlineOpen(false)}>
                ×
              </button>
            </header>
            <input
              value={onlineGoal}
              onChange={(event) => setOnlineGoal(event.target.value)}
              placeholder="Research goal"
            />
            <button
              className="primary full"
              disabled={onlineGoal.trim().length < 8 || startOnline.isPending}
              onClick={() => startOnline.mutate()}
            >
              Find papers
            </button>
            {onlineSearchJob.data ? (
              <JobProgress job={onlineSearchJob.data} compact />
            ) : null}
            <div className="online-paper-list">
              {onlineRows.map((paper) => {
                const id = text(paper.work_id) || text(paper.id);
                const checked = onlineSelected.includes(id);
                return (
                  <label key={id} className={checked ? "selected" : ""}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        setOnlineSelected((current) =>
                          checked
                            ? current.filter((value) => value !== id)
                            : [...current, id],
                        )
                      }
                    />
                    <span>
                      <strong>{itemTitle(paper)}</strong>
                      <small>
                        {String(paper.year ?? "Year unknown")} ·{" "}
                        {text(paper.venue) || text(paper.source)}
                      </small>
                    </span>
                  </label>
                );
              })}
            </div>
            {onlineRows.length ? (
              <button
                className="primary full"
                disabled={!onlineSelected.length || acquireOnline.isPending}
                onClick={() => acquireOnline.mutate()}
              >
                Save {onlineSelected.length} papers
              </button>
            ) : null}
            {onlineAcquireJob.data ? (
              <JobProgress job={onlineAcquireJob.data} compact />
            ) : null}
          </aside>
        </div>
      ) : null}

      {actionNotice && !studio && !selected && !selectedEdge ? (
        <div
          className="research-action-feedback"
          role="status"
          aria-live="polite"
        >
          <span aria-hidden="true">✓</span>
          <strong>{actionNotice}</strong>
          <button
            aria-label="Dismiss message"
            onClick={() => setActionNotice("")}
          >
            ×
          </button>
        </div>
      ) : null}

      {primaryError ? (
        <div className="research-error">
          <ErrorState
            error={primaryError}
            retry={() => {
              session.refetch();
              graph.refetch();
              cloudAtlas.refetch();
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
