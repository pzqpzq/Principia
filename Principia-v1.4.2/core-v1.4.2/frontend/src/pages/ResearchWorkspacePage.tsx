import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { ErrorState, LoadingState } from "../components/AsyncState";
import { CloudStatusControl } from "../components/CloudStatusControl";
import { ResearchRunStatus, finishedResearchStates } from "../components/ResearchRunStatus";
import "./ResearchWorkspaceLayout.css";
import { CustomPrincipleForm } from "../components/CustomPrincipleForm";
import { DataDiscoveryPhases } from "../components/DataDiscoveryPhases";
import { JobProgress, terminalJobStates } from "../components/JobProgress";
import { DialogResizeHandle } from "../components/DialogResizeHandle";
import { DiscoveryActivityDialog } from "../components/DiscoveryActivityDialog";
import { DemoProjectInfo } from "../components/DemoProjectInfo";
import { useDisclosureBounds } from "../components/useDisclosureBounds";
import { FocusDialog, trapDialogFocus } from "../components/FocusDialog";
import { PlainLanguageInterpretation } from "../components/PlainLanguageInterpretation";
import { VisionModelField } from "../components/VisionModelField";
import { savedGraphCamera } from "../components/researchGraphCamera";
import { ScientificText } from "../components/ScientificText";
import { persistGraphOperations, retryableGraphError, QueuedGraphSave, graphSaveMessage } from "../utils/graphPersistence";
import { CalibrationDetails, ComputedEvidence } from "../components/ScientificEvidence";
import { scientificNumber } from "../utils/scientificNumbers";
import { ReceiptFields, SourceEvidence, humanLabel } from "../components/ReceiptFields";
import {
  ResearchGraph,
  type ResearchGraphEdgeSelection,
  type ResearchGraphItem,
  type ResearchGraphViewport,
} from "../components/ResearchGraph";
import {
  queueGraphMutation,
  queuedGraphMutations,
  removeQueuedGraphMutation,
} from "../utils/graphRetryQueue";
import {
  findingInsightLevel,
  findingResultTab,
  INSIGHT_DESCRIPTIONS,
  INSIGHT_LABELS,
  INSIGHT_LEVELS,
  isExecutedSplitRule,
} from "../utils/insightDepth";

type LocalSource = components["schemas"]["LocalSourceResponse"];
type Job = components["schemas"]["JobRecord"];
type UnknownRecord = Record<string, unknown>;
type Tray = "global" | "local" | "meta";
type DataMapTray = "observations" | "principles" | "rules" | "extra";
type Studio = "" | "connection" | "principle";
type DiscoveryTab = "principles" | "observations" | "rules" | "extra";


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
const terminal = finishedResearchStates;
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

function concisePreview(value: unknown, maximum = 240): string {
  const candidate = text(value).trim();
  if (candidate.length <= maximum) return candidate;
  const clipped = candidate.slice(0, maximum + 1);
  const boundary = clipped.lastIndexOf(" ");
  return `${clipped.slice(0, boundary > maximum * 0.72 ? boundary : maximum).trim()}…`;
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

function activityMessage(value: unknown): string {
  return text(value).replace(/ · operational milestones.*$/, "")
    .replace("provider request active", "waiting for model response");
}

function DataActivityFeed({
  events,
  running,
}: {
  events: UnknownRecord[];
  running: boolean;
}) {
  return (
    <div className="data-activity-feed" aria-label="Live discovery activity">
      <header>
        <strong>{running ? "Working now" : "Recorded activity"}</strong>
        <span>
          {events.length
            ? `${events.length} recent events`
            : "Waiting for the first activity receipt"}
        </span>
      </header>
      {events.map((event) => {
        const payload = record(event.payload);
        return (
          <div
            className="data-activity-item"
            key={text(event.event_id) || String(event.sequence)}
          >
            <span aria-hidden="true" />
            <div>
              <strong>
                {text(payload.stage) || text(event.event_type) || "Discovery"}
              </strong>
              <p>
                {activityMessage(payload.message) || "Scientific work receipt recorded."}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ResearchWorkspacePage() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [urlParams, setUrlParams] = useSearchParams();
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
  const dataDockRef = useRef<HTMLElement | null>(null);
  const lastViewportReceiptRef = useRef("");
  const dataDockResizeRef = useRef<{
    pointerId: number;
    x: number;
    y: number;
    width: number;
    height: number;
    top: number;
  } | null>(null);
  const findingCloseRef = useRef<HTMLButtonElement | null>(null);
  const findingDialogRef = useRef<HTMLElement | null>(null);
  const findingReturnFocusRef = useRef<HTMLElement | null>(null);
  const autoSelectedDataTabRef = useRef("");
  const optionsRef = useRef<HTMLDetailsElement | null>(null);
  useDisclosureBounds(optionsRef);
  const [dataActivityOpen, setDataActivityOpen] = useState(false);
  useEffect(() => setDataActivityOpen(false), [sessionId]);
  const areaFilterRef = useRef<HTMLDetailsElement | null>(null);
  const [goal, setGoal] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [sourceQuery, setSourceQuery] = useState("");
  const [confirmEgress, setConfirmEgress] = useState(false);
  const [dataConsentOpen, setDataConsentOpen] = useState(false);
  const [dataProjectMode, setDataProjectMode] = useState<"new" | "replace">("new");
  const [dataProjectTitle, setDataProjectTitle] = useState("");
  const [confirmDataEgress, setConfirmDataEgress] = useState(false);
  const [dataBudget, setDataBudget] = useState<"fast" | "balanced" | "deep">(
    "balanced",
  );
  const [dataStudyId, setDataStudyId] = useState(() => urlParams.get("run") || "");
  const [dataDockCollapsed, setDataDockCollapsed] = useState(
    () => urlParams.get("pane") === "collapsed",
  );
  const [dataDockExpanded, setDataDockExpanded] = useState(
    () => urlParams.get("pane") === "maximized",
  );
  const [mobileSurface, setMobileSurface] = useState<"map" | "discovery">(
    () => {
      const value = urlParams.get("surface");
      return value === "discovery" || value === "results" ? "discovery" : "map";
    },
  );
  const [dataDockSize, setDataDockSize] = useState<{
    width: number;
    height: number;
  } | null>(() => {
    try {
      const saved = JSON.parse(
        window.localStorage.getItem("principia:data-discovery-pane-size") || "null",
      );
      return Number(saved?.width) > 0 && Number(saved?.height) > 0
        ? { width: Number(saved.width), height: Number(saved.height) }
        : null;
    } catch {
      return null;
    }
  });
  const [dataTab, setDataTab] = useState<DiscoveryTab>(() => {
    const value = urlParams.get("tab");
    return value === "observations" || value === "rules" || value === "extra"
      ? value
      : value === "principles" ? "principles" : "observations";
  });
  const initialUrlRecord = urlParams.get("record") || "";
  const [selectedFindingId, setSelectedFindingId] = useState(
    initialUrlRecord.startsWith("finding:") ? initialUrlRecord : "",
  );
  const [selectedRuleId, setSelectedRuleId] = useState(
    /^(?:rule|law|rule-candidate):/.test(initialUrlRecord) ? initialUrlRecord : "",
  );
  const closingDataFindingRef = useRef(false);
  const eventCursor = useRef({ study: "", after: 0 });
  const [streamedDataEvents, setStreamedDataEvents] = useState<UnknownRecord[]>([]);
  const [dataEventStreamConnected, setDataEventStreamConnected] = useState(false);
  const [providerProfile, setProviderProfile] = useState("siliconflow");
  const [providerKey, setProviderKey] = useState("");
  const [providerMessage, setProviderMessage] = useState("");
  const [model, setModel] = useState("deepseek-ai/DeepSeek-V4-Flash");
  const [visionModel, setVisionModel] = useState(() => window.localStorage.getItem("principia:vision-model:siliconflow") || "auto");
  const hydratedVisionStudyRef = useRef("");
  const changeVisionModel = (value: string) => {
    setVisionModel(value);
    window.localStorage.setItem(`principia:vision-model:${providerProfile}`, value.trim() || "auto");
  };
  const [selectedId, setSelectedId] = useState(
    initialUrlRecord && !/^(?:finding|rule|law|rule-candidate):/.test(initialUrlRecord)
      ? initialUrlRecord
      : "",
  );
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
  const [dataMapTray, setDataMapTray] = useState<DataMapTray>("principles");
  const [trayHidden, setTrayHidden] = useState(false);
  const [globalFinderOpen, setGlobalFinderOpen] = useState(false);
  const [globalQuery, setGlobalQuery] = useState("");
  const [globalSearchQuery, setGlobalSearchQuery] = useState("");
  const addingPrinciplesRef = useRef(new Set<string>());
  const [addingPrinciples, setAddingPrinciples] = useState<string[]>([]);
  const [globalFinderMessage, setGlobalFinderMessage] = useState("");
  const [studio, setStudio] = useState<Studio>("");
  const [principleMode, setPrincipleMode] = useState<"ai" | "custom">("ai");
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
  const [atlasSampleId] = useState(() => crypto.randomUUID());
  const [selectedAtlasAreas, setSelectedAtlasAreas] = useState<string[]>([]);
  const closeArtifactDrawer = () => {
    setArtifactDrawer("");
    setVirtualDeleteTarget("");
  };

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const dockResize = dataDockResizeRef.current;
      if (dockResize?.pointerId === event.pointerId) {
        setDataDockSize({
          width: clamp(
            dockResize.width + dockResize.x - event.clientX,
            520,
            window.innerWidth - 310,
          ),
          height: clamp(
            dockResize.height + event.clientY - dockResize.y,
            480,
            window.innerHeight - dockResize.top - 12,
          ),
        });
        return;
      }
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
      if (dataDockResizeRef.current?.pointerId === event.pointerId)
        dataDockResizeRef.current = null;
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
    if (!dataDockSize) return;
    window.localStorage.setItem(
      "principia:data-discovery-pane-size",
      JSON.stringify(dataDockSize),
    );
  }, [dataDockSize]);

  useEffect(() => {
    // Principle dialogs own their backdrop; a document listener would consume
    // the opening click as an outside click. Keep this only for edge inspectors.
    if (!selectedEdge) return;
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
  }, [selectedEdge]);

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
    };
    document.addEventListener("click", closeOptions);
    return () => document.removeEventListener("click", closeOptions);
  }, []);

  useEffect(() => {
    if (!actionNotice) return;
    const timer = window.setTimeout(() => setActionNotice(""), 4_800);
    return () => window.clearTimeout(timer);
  }, [actionNotice]);

  // Shell and workspace share this concise list query. It lets a canonical
  // local-data URL reveal its kind before any large session projection starts,
  // so restoration needs one workspace snapshot instead of session + graph +
  // workspace payloads racing one another.
  const sessionSummaries = useQuery({
    queryKey: ["research-sessions", false],
    queryFn: async () =>
      dataOrThrow(
        await api.GET("/api/v1/research-sessions", {
          params: { query: { project_id: null, include_archived: false } },
        }),
      ) as { items?: UnknownRecord[] },
    refetchInterval: (query) => rows(record(query.state.data).items).some((item) => !terminal.has(text(item.state))) ? 2_000 : false,
  });
  const listedSession =
    sessionSummaries.data?.items?.find(
      (item) => text(item.session_id) === sessionId,
    ) ?? {};
  const listedDataProject = text(listedSession.kind) === "data_discovery";
  const session = useQuery({
    queryKey: ["research-session", sessionId],
    enabled:
      Boolean(sessionId) &&
      sessionSummaries.isSuccess &&
      !listedDataProject,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/research-sessions/{session_id}", {
            params: { path: { session_id: sessionId } },
          }),
        ),
      ),
    refetchInterval: (query) =>
      terminal.has(text(record(query.state.data).state)) ? false : 1_000,
  });
  const sessionData = listedDataProject ? listedSession : record(session.data);
  const sessionDataUpdatedAt = listedDataProject
    ? sessionSummaries.dataUpdatedAt
    : session.dataUpdatedAt;
  const activeRunId = text(sessionData.active_run_id);
  const activeRunState =
    text(sessionData.state) || text(record(sessionData.active_run).state);
  // Data projects used to render the literature Results tray for a moment while
  // their saved study was being restored.  Besides being visually jarring, that
  // transient state exposed a false "branches run" placeholder.  Session kind is
  // persisted independently of the study query, so it is the stable discriminator.
  const isDataProject =
    Boolean(dataStudyId) ||
    text(sessionData.kind) === "data_discovery" ||
    Boolean(text(record(sessionData.active_data_study).study_id));
  const lastWrittenUrl = useRef(urlParams.toString());
  const skipUrlWrite = useRef(false);
  useEffect(() => {
    if (lastWrittenUrl.current === urlParams.toString()) return;
    lastWrittenUrl.current = urlParams.toString();
    skipUrlWrite.current = true;
    setDataStudyId(urlParams.get("run") || "");
    const tab = urlParams.get("tab");
    setDataTab(tab === "principles" || tab === "rules" || tab === "extra" ? tab : "observations");
    const selected = urlParams.get("record") || "";
    setSelectedFindingId(selected.startsWith("finding:") ? selected : "");
    setSelectedRuleId(/^(?:rule|law|rule-candidate):/.test(selected) ? selected : "");
    setSelectedId(selected && !/^(?:finding|rule|law|rule-candidate):/.test(selected) ? selected : "");
    const surface = urlParams.get("surface");
    setMobileSurface(surface === "discovery" || surface === "results" ? "discovery" : "map");
  }, [urlParams]);
  useEffect(() => {
    if (skipUrlWrite.current) { skipUrlWrite.current = false; return; }
    if (!sessionId || !isDataProject || hydratedSessionIdRef.current !== sessionId) return;
    const next = new URLSearchParams(urlParams);
    if (dataStudyId) next.set("run", dataStudyId);
    else next.delete("run");
    next.set("tab", dataTab);
    const selectedRecord = selectedRuleId || selectedFindingId || selectedId;
    if (selectedRecord) next.set("record", selectedRecord);
    else next.delete("record");
    next.set(
      "pane",
      dataDockCollapsed ? "collapsed" : dataDockExpanded ? "maximized" : "open",
    );
    next.set("surface", mobileSurface);
    if (next.toString() !== urlParams.toString()) {
      lastWrittenUrl.current = next.toString();
      setUrlParams(next, { replace: true });
    }
  }, [
    sessionId,
    isDataProject,
    dataStudyId,
    dataTab,
    selectedFindingId,
    selectedRuleId,
    selectedId,
    dataDockCollapsed,
    dataDockExpanded,
    mobileSurface,
    urlParams,
    setUrlParams,
  ]);
  const canonicalWorkspace = useQuery({
    queryKey: ["research-session-workspace", sessionId, dataStudyId],
    enabled: Boolean(sessionId) && isDataProject,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/research-sessions/{session_id}/workspace", {
            params: {
              path: { session_id: sessionId },
              query: { run_id: dataStudyId || "" },
            },
          }),
        ),
      ),
    refetchInterval: (query) => terminal.has(text(record(record(query.state.data).selected_run).state)) ? false : 3_000,
  });
  const graph = useQuery({
    queryKey: ["research-session-graph", sessionId],
    enabled: Boolean(sessionId) && !isDataProject,
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
    queryKey: ["global-webgl-atlas", atlasSampleId, location.key, selectedAtlasAreas.join("|")],
    enabled: !sessionId,
    queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/cloud/graph/sample", {
      params: { query: { areas: selectedAtlasAreas.join(",") } },
    }))),
    staleTime: Infinity,
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
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
    refetchInterval: (query) => {
      const sourceItems = rows(record(query.state.data).sources);
      return sourceItems.some((item) => text(item.readiness) === "understanding")
        ? 2_000
        : 30_000;
    },
  });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: async () =>
      record(dataOrThrow(await api.GET("/api/v1/providers", {}))),
  });
  const dataStudySnapshot = useQuery({
    queryKey: ["data-discovery", dataStudyId],
    enabled: Boolean(dataStudyId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/data-discoveries/{study_id}", {
            params: { path: { study_id: dataStudyId } },
          }),
        ),
      ),
    refetchInterval: (query) =>
      terminal.has(text(record(query.state.data).state)) ? false : dataActivityOpen ? 2_000 : 15_000,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const dataStatus = useQuery({
    queryKey: ["data-discovery-status", dataStudyId],
    enabled: Boolean(dataStudyId) && !terminal.has(text(dataStudySnapshot.data?.state)),
    queryFn: async () => record(dataOrThrow(await api.GET("/api/v1/data-discoveries/{study_id}/status", { params: { path: { study_id: dataStudyId } } }))),
    refetchInterval: 1_500,
  });
  // Live status is a projection, never a write to the detail-query cache.
  // Writing it every 1.5s resets React Query's 2s/15s refetch timer forever.
  const statusForStudy = text(dataStatus.data?.study_id) === dataStudyId ? record(dataStatus.data) : {};
  const dataStudy = {
    ...dataStudySnapshot,
    data: dataStudySnapshot.data ? record({ ...dataStudySnapshot.data, ...statusForStudy, job: { ...record(dataStudySnapshot.data.job), ...record(statusForStudy.job) } }) : undefined,
  };
  useEffect(() => {
    const status = record(dataStatus.data);
    if (text(status.study_id) !== dataStudyId || !dataStudySnapshot.data) return;
    const becameTerminal = terminal.has(text(status.state)) && !terminal.has(text(dataStudySnapshot.data.state));
    if (becameTerminal) {
      void queryClient.invalidateQueries({ queryKey: ["data-discovery", dataStudyId] });
      void queryClient.invalidateQueries({ queryKey: ["research-session-workspace", sessionId] });
      void queryClient.invalidateQueries({ queryKey: ["research-sessions"] });
    }
  }, [dataStatus.dataUpdatedAt, dataStudyId]);
  const dataFindings = useQuery({
    queryKey: ["data-discovery-findings", dataStudyId],
    enabled: Boolean(dataStudyId) && !sessionId,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/data-discoveries/{study_id}/findings", {
            params: { path: { study_id: dataStudyId } },
          }),
        ),
      ),
    refetchInterval: terminal.has(text(dataStudy.data?.state)) ? false : 5_000,
    staleTime: terminal.has(text(dataStudy.data?.state))
      ? Number.POSITIVE_INFINITY
      : 0,
  });
  const dataRules = useQuery({
    queryKey: ["data-discovery-rules", dataStudyId],
    enabled: Boolean(dataStudyId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/data-discoveries/{study_id}/rules", {
            params: { path: { study_id: dataStudyId } },
          }),
        ),
      ),
    refetchInterval: terminal.has(text(dataStudy.data?.state)) ? false : 5_000,
    staleTime: terminal.has(text(dataStudy.data?.state))
      ? Number.POSITIVE_INFINITY
      : 0,
  });
  const selectedScientificLaw = useQuery({
    queryKey: ["data-discovery-law", dataStudyId, selectedRuleId],
    refetchInterval: terminal.has(text(dataStudy.data?.state)) ? false : 5_000,
    enabled: Boolean(dataStudyId && selectedRuleId.startsWith("law:")),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET(
            "/api/v1/data-discoveries/{study_id}/laws/{law_id}",
            {
              params: {
                path: { study_id: dataStudyId, law_id: selectedRuleId },
              },
            },
          ),
        ),
      ),
  });
  const dataEvents = useQuery({
    queryKey: ["data-discovery-events", dataStudyId],
    enabled: Boolean(dataStudyId),
    queryFn: async () => {
      if (eventCursor.current.study !== dataStudyId) eventCursor.current = { study: dataStudyId, after: 0 };
      const payload = record(dataOrThrow(await api.GET("/api/v1/data-discoveries/{study_id}/events", { params: { path: { study_id: dataStudyId }, query: { after: eventCursor.current.after } } })));
      const incoming = rows(payload.items);
      if (eventCursor.current.study === dataStudyId) {
        eventCursor.current.after = Math.max(eventCursor.current.after, ...incoming.map((item) => Number(item.sequence) || 0));
        setStreamedDataEvents((previous) => [...previous, ...incoming].slice(-200));
      }
      return payload;
    },
    refetchInterval: terminal.has(text(dataStudy.data?.state))
      ? false
      : dataEventStreamConnected
        ? false
        : 5_000,
  });
  useEffect(() => {
    setStreamedDataEvents([]);
    setDataEventStreamConnected(false);
    if (!dataStudyId || terminal.has(text(dataStudy.data?.state))) return;
    const source = new EventSource(
      `/api/v1/data-discoveries/${encodeURIComponent(dataStudyId)}/events?after=${eventCursor.current.study === dataStudyId ? eventCursor.current.after : 0}`,
    );
    source.onopen = () => setDataEventStreamConnected(true);
    source.onerror = () => setDataEventStreamConnected(false);
    const eventTypes = [
      "queued",
      "phase",
      "succeeded",
      "interrupted",
      "data_insufficient",
      "activity",
      "heartbeat",
      "analysis_result",
      "program_compiled",
      "scientific_object_compiled",
      "split_frozen",
      "candidate_evaluated",
      "champion_selected",
      "robustness_tested",
      "completed",
      "partial",
      "failed",
      "cancelled",
    ];
    const receive = (event: MessageEvent<string>) => {
      try {
        const value = record(JSON.parse(event.data));
        if (!Object.keys(value).length) return;
        eventCursor.current = { study: dataStudyId, after: Math.max(eventCursor.current.study === dataStudyId ? eventCursor.current.after : 0, Number(value.sequence ?? event.lastEventId ?? 0)) };
        setStreamedDataEvents((current) => {
          const sequence = Number(value.sequence ?? event.lastEventId ?? 0);
          if (
            sequence > 0 &&
            current.some((item) => Number(item.sequence ?? 0) === sequence)
          )
            return current;
          return [...current, value].slice(-80);
        });
        if (terminal.has(text(value.state)) || terminal.has(event.type) || event.type === "completed") {
          void queryClient.invalidateQueries({ queryKey: ["data-discovery-status", dataStudyId] });
          void queryClient.invalidateQueries({ queryKey: ["data-discovery", dataStudyId] });
          setDataEventStreamConnected(false);
          source.close();
        }
      } catch {
        // Polling below remains the explicit fallback for malformed or blocked SSE.
      }
    };
    eventTypes.forEach((eventType) => source.addEventListener(eventType, receive));
    return () => {
      setDataEventStreamConnected(false);
      eventTypes.forEach((eventType) => source.removeEventListener(eventType, receive));
      source.close();
    };
  }, [dataStudyId, text(dataStudy.data?.state)]);
  const dataExtraPrinciples = useQuery({
    queryKey: ["data-discovery-extra-principles", dataStudyId],
    enabled: Boolean(dataStudyId) && !sessionId,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET(
            "/api/v1/data-discoveries/{study_id}/extra-principles",
            { params: { path: { study_id: dataStudyId } } },
          ),
        ),
      ),
    refetchInterval: terminal.has(text(dataStudy.data?.state)) ? false : 5_000,
  });
  const dataLinks = useQuery({
    queryKey: ["data-discovery-links", dataStudyId],
    enabled: Boolean(dataStudyId) && !sessionId,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/data-discoveries/{study_id}/links", {
            params: { path: { study_id: dataStudyId } },
          }),
        ),
      ),
    refetchInterval: terminal.has(text(dataStudy.data?.state)) ? false : 5_000,
  });
  const selectedDataFinding = useQuery({
    queryKey: ["data-discovery-finding", dataStudyId, selectedFindingId],
    enabled: Boolean(dataStudyId && selectedFindingId),
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET(
            "/api/v1/data-discoveries/{study_id}/findings/{finding_id}",
            {
              params: {
                path: {
                  study_id: dataStudyId,
                  finding_id: selectedFindingId,
                },
              },
            },
          ),
        ),
      ),
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
    enabled: Boolean(sessionId) && !isDataProject,
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
    queryKey: ["add-global-principles", globalSearchQuery, sessionId],
    enabled: globalFinderOpen && globalSearchQuery.length >= 2,
    queryFn: async () =>
      record(
        dataOrThrow(
          await api.GET("/api/v1/principles/search", {
            params: { query: {
              q: globalSearchQuery,
              scope: "global",
              intent: "auto",
              session_id: sessionId,
              limit: 40,
            } },
          }),
        ),
      ),
  });
  const submitGlobalFinderSearch = () => {
    const query = globalQuery.trim();
    if (query.length < 2) {
      setGlobalFinderMessage(
        "Enter at least two characters. Scientific acronyms such as AI are supported.",
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
  const visibleSourceRows = useMemo(() => {
    const query = sourceQuery.trim().toLocaleLowerCase();
    return [...sourceRows]
      .filter((source) =>
        !query ||
        `${source.display_name} ${source.readiness} ${Object.keys(source.modality_counts ?? {}).join(" ")}`
          .toLocaleLowerCase()
          .includes(query),
      )
      .sort((left, right) => {
        const leftSelected = selectedSources.includes(left.source_id) ? 0 : 1;
        const rightSelected = selectedSources.includes(right.source_id) ? 0 : 1;
        return (
          leftSelected - rightSelected ||
          left.display_name.localeCompare(right.display_name, undefined, {
            numeric: true,
            sensitivity: "base",
          })
        );
      });
  }, [sources.dataUpdatedAt, sourceQuery, selectedSources]);
  const canonicalRecords = useMemo(() => rows(canonicalWorkspace.data?.records), [canonicalWorkspace.data?.records]);
  const hasCanonicalRecords = Boolean(sessionId && canonicalWorkspace.data);
  const canonicalPayloads = (kind: string) => canonicalRecords.filter((item) => text(item.record_kind) === kind).map((item) => record(item.payload));
  const dataFindingRows = hasCanonicalRecords ? canonicalPayloads("discovery_finding") : rows(dataFindings.data?.items);
  const dataRuleRows = hasCanonicalRecords ? canonicalPayloads("data_rule") : rows(dataRules.data?.items).filter(isExecutedSplitRule);
  const dataRuleCandidateRows = rows(dataRules.data?.candidates).filter(
    (candidate) =>
      text(candidate.record_kind) === "law_candidate" &&
      Boolean(text(candidate.expression_latex)),
  );
  const excludedLegacyEquationCount = Number(
    dataRules.data?.excluded_legacy_equation_count ?? 0,
  );
  const selectedDataRule =
    [...dataRuleRows, ...dataRuleCandidateRows].find(
      (rule) => text(rule.rule_id) === selectedRuleId,
    ) ?? null;
  const selectedDisplayCalibration = record(selectedDataRule?.display_calibration);
  const selectedRuleIsCandidate =
    text(selectedDataRule?.record_kind) === "law_candidate";
  const selectedLawDetail = record(selectedScientificLaw.data);
  const selectedLawCalibrations = rows(selectedLawDetail.calibrations);
  const selectedLawEvaluations = rows(selectedLawDetail.evaluations);
  const selectedLawFrontier = rows(selectedLawDetail.candidate_frontier);
  const dataActivityRows = (
    streamedDataEvents.length ? streamedDataEvents : rows(dataEvents.data?.items)
  ).filter((event, index, all) => text(event.event_type) !== "heartbeat" || index === all.length - 1).slice(-6);
  const dataExtraPrincipleRows = hasCanonicalRecords ? canonicalPayloads("extra_principle") : rows(dataExtraPrinciples.data?.items);
  const dataLinkedPrincipleRows = hasCanonicalRecords ? canonicalPayloads("principle") : rows(dataLinks.data?.principles);
  const dataFoundationRows = hasCanonicalRecords ? canonicalPayloads("meta_principle") : rows(dataLinks.data?.foundations);
  const dataJob = { ...record(dataStudy.data?.job), ...record(dataStatus.data?.job) };
  const liveStudyCounts = record(dataStatus.data?.counts);
  const dataCoverage = record(dataStudy.data?.coverage);
  const expressionSearchReceipts = rows(dataCoverage.expression_search);
  const expressionCount = expressionSearchReceipts.reduce((sum, receipt) => sum + Number(receipt.evaluated_count || 0), 0);
  const bindingBlockers = [...new Set(expressionSearchReceipts.map(receipt => text(receipt.reason)).filter(Boolean))];
  const dataProviderCapability = record(dataCoverage.provider_capability);
  const dataLiveCounts = record(dataCoverage.live_counts);
  const dataExecution = record(dataStudy.data?.execution);
  const dataDegradedCapabilities = rows(dataCoverage.degraded_capabilities);
  const representedNegativeEvidence = new Set(
    dataFindingRows.flatMap((finding) => strings(finding.negative_evidence))
      .map((item) => item.trim().toLocaleLowerCase()),
  );
  const dataNegativeResults = [...new Set(strings(record(dataStudy.data?.report).negative_results))]
    .filter((item) => !representedNegativeEvidence.has(item.trim().toLocaleLowerCase()));
  const selectedReasoningChain = strings(selectedDataFinding.data?.principle_chain).filter(
    (item) => !/^(prn|meta|cand|principle):/i.test(item.trim()),
  );
  const selectedFindingClaim = text(selectedDataFinding.data?.claim);
  const selectedFindingUnexpected = distinctText(
    selectedDataFinding.data?.surprising_result,
    selectedFindingClaim,
  );
  const selectedFindingNontriviality = distinctText(
    selectedDataFinding.data?.nontriviality_basis,
    selectedFindingClaim,
    selectedFindingUnexpected,
  );
  const selectedFindingInterpretation = distinctText(
    selectedDataFinding.data?.interpretation,
    selectedFindingClaim,
    selectedFindingUnexpected,
    selectedFindingNontriviality,
  );
  const selectedFindingPracticalValue = distinctText(
    text(selectedDataFinding.data?.practical_value) ||
      text(selectedDataFinding.data?.significance),
    selectedFindingClaim,
    selectedFindingUnexpected,
    selectedFindingNontriviality,
    selectedFindingInterpretation,
    text(selectedDataFinding.data?.next_validation),
  );
  const selectedFindingTests = rows(selectedDataFinding.data?.tests);
  const selectedScopeTests = selectedFindingTests.slice(0, 3);
  const selectedScopeRemainder = Math.max(
    0,
    selectedFindingTests.length - selectedScopeTests.length,
  );
  const dataHypothesisPortfolio = record(dataCoverage.hypothesis_portfolio);
  const dataPlanningKnowledge = record(dataHypothesisPortfolio.knowledge_retrieval);
  const dataScientificProgramExecution = record(dataCoverage.scientific_program_execution);
  const dataEngineVersion =
    text(dataStudy.data?.engine_version) ||
    text(dataScientificProgramExecution.engine_version);
  const historicalDataRun = dataStudy.data?.historical_rule_evaluation === true;
  const dataResolvedModels = record(dataCoverage.resolved_models);
  const canonicalRuns = rows(canonicalWorkspace.data?.runs);
  // A saved study is the only blocking receipt. Findings, laws, Extra
  // knowledge, and the graph are independent projections and paint as they
  // arrive. Waiting for every projection made a fast local restore feel like a
  // new scientific run and amplified the slowest request.
  const dataStudyLoading = Boolean(dataStudyId) && dataStudy.isLoading;
  const dataResultCollectionsLoading = sessionId ? canonicalWorkspace.isLoading :
    dataFindings.isLoading || dataRules.isLoading || dataExtraPrinciples.isLoading;
  const dataDiscoveryComplete = terminal.has(text(dataStudy.data?.state));
  const dataDiscoveryRunning =
    Boolean(dataStudyId) && !dataStudyLoading && !dataDiscoveryComplete;
  const selectedSourceNames = sourceRows
    .filter((source) => selectedSources.includes(source.source_id))
    .map((source) => source.display_name);
  const canonicalProject = record(canonicalWorkspace.data?.project);
  const projectTitle = isDataProject && text(canonicalProject.title)
    ? text(canonicalProject.title)
    : isDataProject && selectedSourceNames.length
    ? `Discovery · ${selectedSourceNames.slice(0, 2).join(" + ")}${selectedSourceNames.length > 2 ? ` +${selectedSourceNames.length - 2}` : ""}`
    : isDataProject
    ? "Local data discovery"
    : text(sessionData.title) || "Research project";
  const projectSummary = text(record(record(dataStudy.data?.request).portable_demo).description) || (isDataProject && text(canonicalProject.summary)
    ? text(canonicalProject.summary)
    : isDataProject
    ? [
        text(record(dataStudy.data?.request).objective).slice(0, 160),
        Number(dataCoverage.asset_count ?? 0) > 0
          ? `${Number(dataCoverage.asset_count).toLocaleString()} assets`
          : "",
        Number(dataCoverage.executed_test_count ?? 0) > 0
          ? `${Number(dataCoverage.executed_test_count).toLocaleString()} executed tests`
          : "",
        Number(dataCoverage.surviving_finding_count ?? 0) > 0
          ? `${Number(dataCoverage.surviving_finding_count).toLocaleString()} supported findings`
          : "",
        Number(dataCoverage.heldout_rule_count ?? 0) > 0
          ? `${Number(dataCoverage.heldout_rule_count).toLocaleString()} held-out Rule${Number(dataCoverage.heldout_rule_count) === 1 ? "" : "s"}`
          : Number(dataCoverage.rule_count ?? 0) > 0
            ? `${Number(dataCoverage.rule_count).toLocaleString()} exploratory equation${Number(dataCoverage.rule_count) === 1 ? "" : "s"}`
            : "",
      ].filter(Boolean).join(" · ") || "Saved local-data discovery"
    : text(record(sessionData.active_run).goal) || "Saved research workspace");
  const supportedDataFindingRows = dataFindingRows.filter(
    (finding) => text(finding.status) === "supported_candidate",
  );
  const screenedDataFindingRows = dataFindingRows.filter(
    (finding) => text(finding.status) !== "supported_candidate",
  );
  const dataPrincipleFindingRows = supportedDataFindingRows.filter(
    (finding) => findingInsightLevel(finding) === "principle_level",
  );
  const dataObservationGroups = INSIGHT_LEVELS.filter(
    (level) => level !== "principle_level",
  )
    .map((level) => ({
      level,
      items: supportedDataFindingRows.filter(
        (finding) => findingInsightLevel(finding) === level,
      ),
    }))
    .filter((group) => group.items.length > 0);
  const linkedPrincipleById = useMemo(
    () =>
      new Map(
        [...dataLinkedPrincipleRows, ...dataFoundationRows].map((item) => [
          text(item.id) || text(item.principle_id),
          item,
        ]),
      ),
    [dataLinks.dataUpdatedAt, canonicalWorkspace.dataUpdatedAt],
  );

  useEffect(() => {
    if (closingDataFindingRef.current) {
      if (!selectedRuleId && !selectedFindingId)
        closingDataFindingRef.current = false;
      return;
    }
    if (selectedRuleId && selectedDataRule) {
      const findingId = text(selectedDataRule.finding_id);
      if (findingId !== selectedFindingId) setSelectedFindingId(findingId);
    }
  }, [selectedRuleId, selectedDataRule, selectedFindingId]);

  useEffect(() => {
    if (
      !dataDiscoveryComplete ||
      !(hasCanonicalRecords || dataFindings.isFetched) ||
      autoSelectedDataTabRef.current === dataStudyId
    )
      return;
    autoSelectedDataTabRef.current = dataStudyId;
    const requestedTab = urlParams.get("tab");
    if (
      urlParams.get("run") === dataStudyId &&
      (requestedTab === "principles" ||
        requestedTab === "observations" ||
        requestedTab === "rules" ||
        requestedTab === "extra")
    ) {
      setDataTab(requestedTab);
      return;
    }
    if (dataPrincipleFindingRows.length) setDataTab("principles");
    else if (
      dataObservationGroups.length ||
      screenedDataFindingRows.length ||
      dataNegativeResults.length
    )
      setDataTab("observations");
    else if (dataRuleRows.length) setDataTab("rules");
    else if (dataExtraPrincipleRows.length) setDataTab("extra");
  }, [
    dataStudyId,
    dataDiscoveryComplete,
    dataFindings.isFetched,
    dataFindings.dataUpdatedAt,
    dataRules.dataUpdatedAt,
    dataExtraPrinciples.dataUpdatedAt,
  ]);

  const openDataFinding = (findingId: string, ruleId = "") => {
    findingReturnFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelectedRuleId(ruleId);
    setSelectedFindingId(findingId);
  };
  const closeDataFinding = () => {
    // Prevent the Rule-to-Finding hydration effect from reopening the dialog
    // while React and the URL projection settle the same close transition.
    closingDataFindingRef.current = true;
    setSelectedRuleId("");
    setSelectedFindingId("");
    window.requestAnimationFrame(() => findingReturnFocusRef.current?.focus());
  };

  useEffect(() => {
    if (!selectedFindingId && !selectedRuleId) return;
    window.requestAnimationFrame(() => findingCloseRef.current?.focus());
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeDataFinding();
      if (event.key !== "Tab" || !findingDialogRef.current) return;
      const focusable = [...findingDialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], details > summary, [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedFindingId, selectedRuleId]);
  const graphRows = useMemo(
    () =>
      sessionId
        ? rows(
            isDataProject
              ? record(canonicalWorkspace.data?.graph).items
              : graph.data?.items,
          ).map(sessionGraphItem)
        : rows(cloudAtlas.data?.nodes).map((item, index) =>
            sessionGraphItem(
              { ...item, principle_id: item.id, payload: item },
              index,
            ),
          ),
    [
      sessionId,
      isDataProject,
      graph.dataUpdatedAt,
      canonicalWorkspace.dataUpdatedAt,
      cloudAtlas.dataUpdatedAt,
    ],
  );
  const dataMapGroups = useMemo<Record<DataMapTray, ResearchGraphItem[]>>(
    () => ({
      observations: graphRows.filter((item) => canonicalRecords.some((record) => text(record.record_id) === item.principle_id && text(record.category) === "observations")),
      principles: graphRows.filter((item) => canonicalRecords.some((record) => text(record.record_id) === item.principle_id && ["principles", "global_principles"].includes(text(record.category)))),
      rules: graphRows.filter((item) => item.record_kind === "data_rule"),
      extra: graphRows.filter((item) => item.record_kind === "extra_principle"),
    }),
    [graphRows, canonicalRecords],
  );
  const dataMapItems = dataMapGroups[dataMapTray];
  const dataMapTotal = Object.values(dataMapGroups).reduce(
    (total, items) => total + items.length,
    0,
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
  const sessionGraphProjection = isDataProject
    ? record(canonicalWorkspace.data?.graph)
    : record(graph.data);
  const sessionTheme =
    text(sessionGraphProjection.theme) === "deep-space"
      ? "deep-space"
      : "daylight";
  const persistedViewport = record(sessionGraphProjection.viewport);
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
      ...dataLinkedPrincipleRows,
      ...dataFoundationRows.map((item) => ({ ...item, principle_class: "meta" })),
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
  }, [graphRows, cartCandidates, trayItems, globalFinder.dataUpdatedAt, dataLinkedPrincipleRows, dataFoundationRows]);
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
    for (const edge of [...rows(sessionGraphProjection.edges), ...virtualEdges]) {
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
    const remoteRevision = Number(
      isDataProject
        ? record(canonicalWorkspace.data?.graph).revision
        : graph.data?.revision,
    );
    if (Number.isFinite(remoteRevision))
      revisionBySessionRef.current.set(
        sessionId,
        Math.max(
          revisionBySessionRef.current.get(sessionId) ?? 0,
          remoteRevision,
        ),
      );
  }, [
    sessionId,
    isDataProject,
    graph.dataUpdatedAt,
    canonicalWorkspace.dataUpdatedAt,
  ]);

  useEffect(() => {
    if (!sessionId) {
      if (hydratedSessionIdRef.current) {
        hydratedSessionIdRef.current = "";
        setGoal("");
        setSelectedSources([]);
        setSelectedId("");
        setSelectedFindingId("");
        setSelectedRuleId("");
        setTray("global");
        setDataMapTray("principles");
        setTrayHidden(false);
        setDataStudyId("");
      }
      return;
    }
    if (!Object.keys(sessionData).length || hydratedSessionIdRef.current === sessionId)
      return;
    const active = record(sessionData.active_run);
    hydratedSessionIdRef.current = sessionId;
    setGoal(text(active.goal));
    const requestedSurface = urlParams.get("surface");
    setMobileSurface(requestedSurface === "discovery" || requestedSurface === "results" ? "discovery" : "map");
    setDataDockCollapsed(requestedSurface !== "discovery" && requestedSurface !== "results");
    setSelectedSources(strings(sessionData.source_ids));
    const restoredRecord = urlParams.get("record") || "";
    setSelectedId(restoredRecord && !/^(?:finding|rule|law|rule-candidate):/.test(restoredRecord) ? restoredRecord : "");
    setSelectedFindingId((urlParams.get("record") || "").startsWith("finding:") ? urlParams.get("record") || "" : "");
    setSelectedRuleId(/^(?:rule|law|rule-candidate):/.test(urlParams.get("record") || "") ? urlParams.get("record") || "" : "");
    setTray("global");
    setDataMapTray("principles");
    setTrayHidden(false);
    const requestedRun = urlParams.get("run") || "";
    const restoredStudyId =
      requestedRun || text(record(sessionData.active_data_study).study_id);
    setDataStudyId(restoredStudyId);
    if (restoredStudyId) {
      const requestedTab = urlParams.get("tab");
      setDataTab(
        requestedTab === "observations" || requestedTab === "rules" || requestedTab === "extra"
          ? requestedTab
          : "principles",
      );
    }
    if (text(sessionData.provider_profile_id))
      setProviderProfile(text(sessionData.provider_profile_id));
    if (text(sessionData.model)) setModel(text(sessionData.model));
  }, [sessionId, sessionDataUpdatedAt, urlParams]);

  useEffect(() => {
    const request = record(dataStudy.data?.request);
    if (!dataStudyId || !Object.keys(request).length || hydratedVisionStudyRef.current === dataStudyId) return;
    hydratedVisionStudyRef.current = dataStudyId;
    setVisionModel(text(request.vision_model) || "auto");
  }, [dataStudyId, dataStudy.dataUpdatedAt]);

  useEffect(() => {
    if (!isDataProject) return;
    const restored =
      text(record(canonicalWorkspace.data?.selected_run).study_id) ||
      text(record(canonicalWorkspace.data?.project).preferred_study_id);
    if (restored && !dataStudyId) setDataStudyId(restored);
  }, [dataStudyId, isDataProject, canonicalWorkspace.dataUpdatedAt]);

  useEffect(() => {
    const applyProviderModel = (event: Event) => {
      const detail = (event as CustomEvent<{ providerId?: string; model?: string }>).detail;
      if (detail?.providerId) {
        setProviderProfile(detail.providerId);
        setVisionModel(window.localStorage.getItem(`principia:vision-model:${detail.providerId}`) || "auto");
      }
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
    onSuccess: (value) => {
      const id = text(value.session_id);
      queryClient.setQueryData(["research-session", id], value);
      void queryClient.invalidateQueries({ queryKey: ["research-sessions"] });
      navigate(`/research/${encodeURIComponent(id)}`);
    },
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
    onSuccess: (value) => {
      const added = rows(record(value).sources).map((item) => text(item.source_id));
      setSelectedSources((current) => [...new Set([...current, ...added.filter(Boolean)])]);
      void queryClient.invalidateQueries({ queryKey: ["research-sources"] });
      setRunNotice(
        added.filter(Boolean).length
          ? `${added.filter(Boolean).length} local folder${added.filter(Boolean).length === 1 ? "" : "s"} added and selected.`
          : "No folder was selected; the current research was left unchanged.",
      );
    },
    onError: (error) =>
      setRunNotice(
        error instanceof Error
          ? `Local folders were not added: ${error.message}`
          : "Local folders were not added.",
      ),
  });
  const startDataDiscovery = useMutation({
    mutationFn: async () =>
      record(
        dataOrThrow(
          await api.POST("/api/v1/data-discoveries", {
            body: {
              source_ids: selectedSources,
              objective: goal.trim(),
              provider: providerProfile,
              reasoning_model: model || "auto",
              vision_model: visionModel.trim() || "auto",
              knowledge_scope: "combined",
              prior_art: "survivors",
              budget: dataBudget,
              session_id: sessionId || "",
              project_mode: sessionId ? dataProjectMode : "new",
              project_title: dataProjectMode === "new" ? dataProjectTitle.trim() : "",
              expected_session_revision: sessionId && dataProjectMode === "replace" ? Number(sessionData.revision) || undefined : undefined,
              egress_confirmed: confirmDataEgress,
            },
          }),
        ),
      ),
    onSuccess: async (value) => {
      queryClient.setQueryData(["data-discovery", text(value.study_id)], value);
      setDataStudyId(text(value.study_id));
      setDataDockCollapsed(false);
      setDataDockExpanded(false);
      setDataTab("principles");
      autoSelectedDataTabRef.current = "";
      setSelectedFindingId("");
      setSelectedRuleId("");
      setDataConsentOpen(false);
      setConfirmDataEgress(false);
      setRunNotice("Data discovery started. Source bytes remain read-only.");
      await queryClient.invalidateQueries({ queryKey: ["research-projects"] });
      await queryClient.invalidateQueries({ queryKey: ["research-sessions"] });
      const targetSession = text(value.session_id);
      if (targetSession)
        navigate(`/research/${encodeURIComponent(targetSession)}?run=${encodeURIComponent(text(value.study_id))}&surface=map`);
    },
  });
  const cancelDataDiscovery = useMutation({
    mutationFn: async (studyId: string) => record(dataOrThrow(await api.POST("/api/v1/data-discoveries/{study_id}/cancel", { params: { path: { study_id: studyId } } }))),
    onSuccess: async (status, studyId) => {
      queryClient.setQueryData(["data-discovery-status", studyId], status);
      queryClient.setQueryData<UnknownRecord>(["data-discovery", studyId], previous => previous ? { ...previous, ...status, job: { ...record(previous.job), ...record(status.job) } } : previous);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["data-discovery", studyId] }),
        queryClient.invalidateQueries({ queryKey: ["data-discovery-status", studyId] }),
        queryClient.invalidateQueries({ queryKey: ["research-sessions"] }),
      ]);
    },
  });
  const createDataPrincipleDraft = useMutation({
    mutationFn: async (findingId: string) =>
      dataOrThrow(
        await api.POST(
          "/api/v1/data-discoveries/{study_id}/findings/{finding_id}/principle-draft",
          {
            params: {
              path: { study_id: dataStudyId, finding_id: findingId },
            },
          },
        ),
      ),
    onSuccess: () =>
      void selectedDataFinding.refetch(),
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
    const graphQueryKey = isDataProject
      ? ["research-session-workspace", sessionId, dataStudyId]
      : ["research-session-graph", sessionId];
    queryClient.setQueryData<UnknownRecord>(
      graphQueryKey,
      (currentValue) => {
        const envelope = record(currentValue);
        const current = isDataProject ? record(envelope.graph) : envelope;
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
        if (!changed) return currentValue;
        const nextGraph = {
          ...current,
          items: nextItems,
          viewport: nextViewport,
          theme: nextTheme,
        };
        if (!isDataProject) return nextGraph;
        let nextRecords = rows(envelope.records);
        for (const operation of operations) {
          const id = text(operation.principle_id);
          if (operation.action === "add" && !nextRecords.some(item => text(item.record_id) === id)) {
            const payload = record(operation.payload);
            nextRecords = [...nextRecords, {
              record_id: id, record_kind: payload.principle_class === "meta" ? "meta_principle" : "principle",
              category: "global_principles", origin: "user_added",
              payload: { ...payload, workspace_origin: "user_added" },
            }];
          } else if (operation.action === "remove") {
            nextRecords = nextRecords.filter(item => text(item.record_id) !== id || item.origin !== "user_added");
          }
        }
        const nextCounts: Record<string, number> = {};
        for (const item of nextRecords) nextCounts[text(item.category)] = (nextCounts[text(item.category)] ?? 0) + 1;
        return { ...envelope, records: nextRecords, counts: nextCounts, graph: nextGraph };
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
        try {
          // Replay earlier device saves before this new edit, on the same chain.
          for (const queued of await queuedGraphMutations(targetSessionId)) {
            try {
              await persistGraphOperations(targetSessionId, queued.operations, revisionBySessionRef.current);
              await removeQueuedGraphMutation(queued.id);
            } catch (error) {
              if (retryableGraphError(error)) throw error;
              await removeQueuedGraphMutation(queued.id);
              setActionNotice(graphSaveMessage(error));
            }
          }
          await persistGraphOperations(targetSessionId, operations, revisionBySessionRef.current);
          if (operations.some(operation => ["add", "remove"].includes(text(operation.action)))) {
            await queryClient.invalidateQueries({ queryKey: ["research-session-graph", targetSessionId] });
            await queryClient.invalidateQueries({ queryKey: ["research-session-workspace", targetSessionId] });
          }
        } catch (error) {
          if (retryableGraphError(error)) {
            try {
              await queueGraphMutation({ sessionId: targetSessionId,
                expectedRevision: revisionBySessionRef.current.get(targetSessionId) ?? 0, operations });
            } catch {
              throw new Error("Device storage is unavailable. Reconnect and try the change again.");
            }
            throw new QueuedGraphSave();
          }
          void queryClient.invalidateQueries({ queryKey: ["research-session-graph", targetSessionId] });
          void queryClient.invalidateQueries({ queryKey: ["research-session-workspace", targetSessionId] });
          throw error;
        }
      });
    saveChain.current = next.catch(error => { setActionNotice(graphSaveMessage(error)); });
    return next;
  };

  const addOrRevealPrinciple = async (
    item: UnknownRecord,
    present: boolean,
  ) => {
    const id =
      text(item.id) || text(item.principle_id) || text(item.candidate_id);
    if (!id || addingPrinciplesRef.current.has(id)) return;
    addingPrinciplesRef.current.add(id);
    setAddingPrinciples([...addingPrinciplesRef.current]);
    setGlobalFinderMessage("");
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
      if (!globalFinderOpen) setSelectedId(id);
      setDataMapTray("principles");
      setMobileSurface("map");
      setDataDockCollapsed(true);
      setActionNotice(
        present
          ? "This Principle is already on the map and is now centered."
          : "Principle added to the study map.",
      );
      setGlobalFinderMessage(present ? "Centered on the map. Close search when you are ready to explore it." : "Added to the map. You can continue adding Principles.");
    } catch (error) {
      setGlobalFinderMessage(graphSaveMessage(error));
      setActionNotice(graphSaveMessage(error));
    } finally {
      addingPrinciplesRef.current.delete(id);
      setAddingPrinciples([...addingPrinciplesRef.current]);
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
      } catch (error) {
        setActionNotice(graphSaveMessage(error));
      }
    }
    setSelectedId(metaId);
    setFocusTarget({ id: metaId, request: Date.now() });
  };

  const settleViewport = (viewport: ResearchGraphViewport) => {
    if (sessionId) {
      const values = [
        viewport.x,
        viewport.y,
        viewport.angle,
        viewport.ratio,
      ];
      const persisted = [
        Number(persistedViewport.x ?? 0.5),
        Number(persistedViewport.y ?? 0.5),
        Number(persistedViewport.angle ?? 0),
        Number(persistedViewport.ratio ?? 3),
      ];
      const unchanged = values.every(
        (value, index) => Math.abs(value - persisted[index]) < 0.0001,
      );
      const receipt = `${sessionId}:${values.map((value) => value.toFixed(5)).join(":")}`;
      if (unchanged || lastViewportReceiptRef.current === receipt) return;
      lastViewportReceiptRef.current = receipt;
      void sendGraphOperations([
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

  };

  useEffect(() => {
    if (!sessionId) return;
    const remoteRevision = Number(
      isDataProject
        ? record(canonicalWorkspace.data?.graph).revision
        : graph.data?.revision,
    );
    if (!Number.isFinite(remoteRevision)) return;
    const flush = () => {
      const next = saveChain.current.catch(() => undefined).then(async () => {
        const queuedOperations = await queuedGraphMutations(sessionId);
        if (!queuedOperations.length) return;
        let applied = false;
        for (const queued of queuedOperations) {
          try {
            await persistGraphOperations(sessionId, queued.operations, revisionBySessionRef.current);
            await removeQueuedGraphMutation(queued.id);
            applied = true;
          } catch (error) {
            if (retryableGraphError(error)) break;
            await removeQueuedGraphMutation(queued.id);
            setActionNotice(graphSaveMessage(error));
          }
        }
        if (applied) {
          void queryClient.invalidateQueries({ queryKey: ["research-session-graph", sessionId] });
          void queryClient.invalidateQueries({ queryKey: ["research-session-workspace", sessionId] });
        }
      });
      saveChain.current = next.catch(error => setActionNotice(graphSaveMessage(error)));
    };
    window.addEventListener("online", flush);
    void flush();
    return () => window.removeEventListener("online", flush);
  }, [
    sessionId,
    isDataProject,
    graph.dataUpdatedAt,
    canonicalWorkspace.dataUpdatedAt,
  ]);

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

  const saveVirtualLocally = async (item: UnknownRecord, index: number, provenance?: UnknownRecord) => {
    const proposal = record(
      item.proposal,
    ) as components["schemas"]["VirtualPrincipleProposal"];
    const generation = provenance ?? record(
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

  const activeRun = record(sessionData.active_run);
  const branches = Object.entries(record(activeRun.branches));
  const onlineRows = rows(onlineSearch.data?.results);
  const primaryError =
    session.error ??
    sessionSummaries.error ??
    canonicalWorkspace.error ??
    cancelDataDiscovery.error ??
    graph.error ??
    cloudAtlas.error ??
    sources.error ??
    createSession.error ??
    startAnotherRun.error ??
    startDataDiscovery.error ??
    dataStudy.error ??
    saveProviderKey.error;

  useEffect(() => {
    const state = text(dataStudy.data?.state);
    if (!dataStudyId || !terminal.has(state)) return;
    // The final finding can be committed in the same instant that the study
    // becomes terminal. Force one post-terminal read so the last pre-terminal
    // empty response cannot strand the UI at "0 findings".
    void queryClient.invalidateQueries({
      queryKey: ["data-discovery-findings", dataStudyId],
    });
    void queryClient.invalidateQueries({ queryKey: ["data-discovery-rules", dataStudyId] });
    void queryClient.invalidateQueries({ queryKey: ["research-session-workspace", sessionId] });
    void queryClient.invalidateQueries({
      queryKey: ["data-discovery-links", dataStudyId],
    });
    void queryClient.invalidateQueries({
      queryKey: ["data-discovery-extra-principles", dataStudyId],
    });
    if (sessionId) {
      void queryClient.invalidateQueries({
        queryKey: ["research-session", sessionId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["research-session-graph", sessionId],
      });
    }
  }, [dataStudyId, text(dataStudy.data?.state), queryClient, sessionId]);

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
  }, [sessionId, sessionDataUpdatedAt]);

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
      className={`research-workspace flow-layout ${sessionId ? "has-session" : "is-new"} ${isDataProject ? "data-project" : ""} ${trayHidden ? "tray-hidden" : ""} ${studio ? "studio-open" : ""} mobile-surface-${mobileSurface}`}
    >
      <div className="research-toolbar">
      <header
        className={`research-command-bar ${sessionId ? "compact" : "welcome"} ${isDataProject ? "data-project" : ""}`}
      >
        {!sessionId ? (
          <div className="research-command-intro">
            <span className="eyebrow">New research</span>
            <h1>
              Start a discovery
            </h1>
            <p>
              Add data to explore quantitative Rules, or enter a research goal.
            </p>
          </div>
        ) : (
          <div className="research-project-context" aria-label="Current research project">
            <span>{isDataProject ? (record(dataStudy.data?.request).portable_demo ? "Public demo project" : "Local data project") : "Research project"}
              {record(dataStudy.data?.request).portable_demo ? <DemoProjectInfo demo={record(record(dataStudy.data?.request).portable_demo)} /> : null}
            </span>
            <h1 title={projectTitle}>{projectTitle}</h1>
            <p title={projectSummary}>{projectSummary}</p>
          </div>
        )}
        {isDataProject ? <button className="primary discover-again" disabled={!dataStudy.data || dataStudyLoading || dataDiscoveryRunning || startDataDiscovery.isPending}
          onClick={() => {
            setDataProjectMode("new"); setDataProjectTitle(`${projectTitle} · New discovery`);
            setGoal(text(record(dataStudy.data?.request).objective));
            setSelectedSources(current => current.filter(id => sourceRows.some(source => source.source_id === id && source.status !== "demo")));
            setConfirmDataEgress(false); startDataDiscovery.reset(); setDataConsentOpen(true);
          }}>Discover again</button> : null}
        {!isDataProject ? <form className="research-composer"
          onSubmit={(event) => {
            event.preventDefault();
            if (selectedSources.length && !sessionId) {
              if (!dataStudyLoading && !dataDiscoveryRunning && !startDataDiscovery.isPending) {
                setConfirmDataEgress(false);
                setDataConsentOpen(true);
              }
              return;
            }
            if (goal.trim().length < 8) return;
            if (selectedSources.length && !Boolean(profile.configured)) {
              requestProviderSetup();
              return;
            }
            sessionId ? startAnotherRun.mutate() : createSession.mutate();
          }}
        >
          {!sessionId ? <button type="button" className="data-discover-button" onClick={(event) => { event.stopPropagation(); if (optionsRef.current) { optionsRef.current.open = true; optionsRef.current.querySelector<HTMLElement>("button")?.focus(); } }}>Add data</button> : null}
          <input
            autoFocus={!sessionId}
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder={selectedSources.length ? "Optional objective for your data" : "Your research goal"}
            aria-label="Research goal"
          />
          {!selectedSources.length || sessionId ? <button
            className="primary"
            disabled={
              goal.trim().length < 8 ||
              createSession.isPending ||
              startAnotherRun.isPending ||
              Boolean(
                sessionId &&
                  activeRunState &&
                  !terminal.has(activeRunState),
              )
            }
          >
            {createSession.isPending || startAnotherRun.isPending
              ? "Starting…"
              : sessionId
                ? "Search again"
                : "Explore"}
          </button> : null}
          {selectedSources.length ? (
            <button
              type="button"
              className="primary"
              disabled={
                dataStudyLoading || dataDiscoveryRunning || startDataDiscovery.isPending
              }
              onClick={() => {
                setConfirmDataEgress(false);
                setDataConsentOpen(true);
              }}
            >
              {dataStudyLoading
                ? "Restoring saved discovery…"
                : dataDiscoveryRunning
                  ? "Discovering…"
                  : "Discover data"}
            </button>
          ) : null}
        </form> : null}
        <details className="research-input-options" ref={optionsRef}>
          <summary>
            Sources & model{" "}
            <span>
              {record(dataStudy.data?.request).portable_demo
                ? "Bundled public evidence"
                : selectedSources.length
                ? `${selectedSources.length} local folder${selectedSources.length === 1 ? "" : "s"}`
                : "Global Cloud only"}
            </span>
          </summary>
          <div className="research-options-popover">
            <div className="research-option-actions">
              <button disabled={addFolders.isPending} onClick={() => addFolders.mutate()}>
                {addFolders.isPending ? "Opening folder picker…" : "Add local folders"}
              </button>
              <button
                onClick={() => {
                  setOnlineGoal(goal);
                  setOnlineOpen(true);
                }}
              >
                Find papers online
              </button>
              {selectedSources.length ? (
                <button
                  type="button"
                  className="primary research-options-done"
                  onClick={() => optionsRef.current?.removeAttribute("open")}
                >
                  Done
                </button>
              ) : null}
            </div>
            <div className="research-source-chips">
              {sourceRows.length > 6 ? (
                <label className="research-source-filter">
                  <span className="visually-hidden">Filter local data folders</span>
                  <input
                    type="search"
                    value={sourceQuery}
                    onChange={(event) => setSourceQuery(event.target.value)}
                    placeholder="Find a folder, modality, or status…"
                  />
                  <small>{visibleSourceRows.length} of {sourceRows.length}</small>
                </label>
              ) : null}
              {visibleSourceRows.map((source) => (
                <label key={source.source_id} title={source.display_name}>
                  <input
                    type="checkbox"
                    disabled={source.status === "demo"}
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
                    <small>
                      {source.status === "demo" ? "Bundled evidence · local data not connected" : source.asset_count
                        ? `${source.analyzable_count}/${source.asset_count} analyzable · ${source.readiness.replace("_", " ")}`
                        : `${source.document_count} papers · not profiled`}
                    </small>
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
              {!visibleSourceRows.length ? (
                <p className="research-source-empty">No local folder matches this filter.</p>
              ) : null}
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
                  setVisionModel(window.localStorage.getItem(`principia:vision-model:${providerId}`) || "auto");
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
            <VisionModelField provider={providerProfile} configured={Boolean(profile.configured)} value={visionModel} onChange={changeVisionModel} models={strings(profile.vision_models)} defaultModel={text(profile.default_vision_model)} />
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

      {runNotice && !(sessionId && (isDataProject || !terminal.has(activeRunState))) ? (
        <div
          className={`research-run-notice ${startAnotherRun.isPending ? "active" : ""}`}
          role="status"
          aria-live="polite"
        >
          {startAnotherRun.isPending ? (
            <span className="spinner" />
          ) : (
            <span aria-hidden="true">{addFolders.error || startAnotherRun.error ? "!" : "✓"}</span>
          )}
          <strong>{runNotice}</strong>
          {!startAnotherRun.isPending ? (
            <button
              aria-label="Dismiss notice"
              onClick={() => setRunNotice("")}
            >
              ×
            </button>
          ) : null}
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
              canonicalWorkspace.refetch();
              sources.refetch();
            }}
          />
        </div>
      ) : null}
      {sessionId && ((isDataProject && Boolean(dataStudyId)) || (!isDataProject && !terminal.has(activeRunState))) ? (
        <ResearchRunStatus
          kind={isDataProject ? "discovery" : "research"}
          state={isDataProject ? text(dataStudy.data?.state) || activeRunState || "queued" : activeRunState || "queued"}
          phase={text(dataStudy.data?.phase)}
          message={isDataProject ? activityMessage(dataJob.status_message) : terminal.has(text(record(sessionData.active_run).state)) ? "Preparing the map and publishing search results…" : ""}
          startedAt={text(dataStudy.data?.created_at) || text(record(sessionData.active_run).created_at)}
          lastActivityAt={text(dataJob.last_activity_at) || text(dataStudy.data?.updated_at)}
          tests={Number(liveStudyCounts.tests ?? dataCoverage.executed_test_count ?? 0)}
          findings={Number(liveStudyCounts.supported_findings ?? dataFindingRows.length)}
          connectionError={(dataStatus.error || dataStudy.error || session.error) instanceof Error ? ((dataStatus.error || dataStudy.error || session.error) as Error).message : ""}
          cancelling={cancelDataDiscovery.isPending || text(dataJob.state) === "cancelling"}
          onCancel={isDataProject && dataStudyId ? () => cancelDataDiscovery.mutate(dataStudyId) : undefined}
          onActivity={isDataProject ? () => setDataActivityOpen(true) : undefined}
          onResults={isDataProject ? () => { setMobileSurface("discovery"); setDataDockCollapsed(false); } : undefined}
          onRetry={() => { void dataStatus.refetch(); void dataStudy.refetch(); void session.refetch(); }}
        />
      ) : null}
      {isDataProject ? (
        <nav className="mobile-workspace-switcher" aria-label="Project workspace view">
          <button
            className={mobileSurface === "map" ? "selected" : ""}
            aria-pressed={mobileSurface === "map"}
            onClick={() => {
              setMobileSurface("map");
              setTrayHidden(false);
              setDataDockCollapsed(true);
            }}
          >
            <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="3" width="5" height="5" rx="1"/><rect x="12" y="3" width="5" height="5" rx="1"/><rect x="3" y="12" width="5" height="5" rx="1"/><rect x="12" y="12" width="5" height="5" rx="1"/></svg>Map
          </button>
          <button
            className={mobileSurface === "discovery" ? "selected" : ""}
            aria-pressed={mobileSurface === "discovery"}
            onClick={() => {
              setMobileSurface("discovery");
              setDataDockCollapsed(false);
            }}
          >
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4h12M4 10h12M4 16h8"/></svg>Results
          </button>
        </nav>
      ) : null}

      </div>
      <div className="research-surface">
      {dataConsentOpen ? (
        <div className="research-modal data-consent-modal" role="presentation">
          <article role="dialog" aria-modal="true" aria-labelledby="data-consent-title">
            <header>
              <div>
                <small>{sessionId ? "New discovery attempt" : "One-run permission"}</small>
                <h2 id="data-consent-title">{sessionId ? "Discover again" : "Discover from local data"}</h2>
              </div>
              <button
                aria-label="Cancel data discovery"
                onClick={() => {
                  setDataConsentOpen(false);
                  setConfirmDataEgress(false);
                }}
              >
                ×
              </button>
            </header>
            {sessionId ? <div className="discovery-setup-fields">
              <label><span>Research goal</span><textarea autoFocus value={goal} onChange={event => setGoal(event.target.value)} rows={3} maxLength={4000} /></label>
              <fieldset className="discovery-destination"><legend>Where should the new results go?</legend>
                <label><input type="radio" name="discovery-destination" checked={dataProjectMode === "new"} onChange={() => setDataProjectMode("new")} /><span><strong>New project</strong><small>Keep this project and explore a separate attempt.</small></span></label>
                <label><input type="radio" name="discovery-destination" checked={dataProjectMode === "replace"} onChange={() => setDataProjectMode("replace")} /><span><strong>Overwrite current project</strong><small>Show the new run here. Earlier runs remain in its research history.</small></span></label>
              </fieldset>
              {dataProjectMode === "new" ? <label><span>Project name</span><input value={dataProjectTitle} onChange={event => setDataProjectTitle(event.target.value)} maxLength={240} /></label> : null}
              <fieldset className="discovery-source-choices"><legend>Local data</legend>
                {record(dataStudy.data?.request).portable_demo ? <p>This demo includes its equations and recorded evidence. Add a local data folder to run a new discovery; the original dataset is not bundled.</p> : null}
                {sourceRows.filter(source => source.status !== "demo").map(source => <label key={source.source_id}><input type="checkbox" checked={selectedSources.includes(source.source_id)} onChange={event => setSelectedSources(current => event.target.checked ? [...new Set([...current, source.source_id])] : current.filter(id => id !== source.source_id))} /><span>{source.display_name}</span></label>)}
              </fieldset>
              <button className="discovery-add-folder" disabled={addFolders.isPending} onClick={() => addFolders.mutate()}>{addFolders.isPending ? "Opening folder picker…" : "Add local folders"}</button>
              {addFolders.error ? <p role="alert" className="field-error">{addFolders.error instanceof Error ? addFolders.error.message : "The folder could not be added."}</p> : null}
              <div className="discovery-model-fields">
                <label><span>LLM provider</span><select value={providerProfile} onChange={event => {
                  const id = event.target.value; const next = record(providerRows.find(row => providerIdentifier(row) === id));
                  setProviderProfile(id); setModel(text(next.default_model) || "auto");
                  setVisionModel(window.localStorage.getItem(`principia:vision-model:${id}`) || "auto");
                }}>{providerRows.map(row => <option key={providerIdentifier(row)} value={providerIdentifier(row)}>{text(row.label) || providerIdentifier(row)}</option>)}</select></label>
                <label><span>Reasoning model</span><input value={model} list="discovery-model-options" onChange={event => setModel(event.target.value)} /><datalist id="discovery-model-options">{strings(profile.models).map(value => <option key={value} value={value} />)}</datalist></label>
                <VisionModelField provider={providerProfile} configured={Boolean(profile.configured)} value={visionModel} onChange={changeVisionModel} models={strings(profile.vision_models)} defaultModel={text(profile.default_vision_model)} />
              </div>
            </div> : null}
            <p>
              Principia inventories files locally, executes analyses in the workspace,
              and sends only compact profiles, selected excerpts, Principle cards, and
              bounded derived previews to the configured provider.
            </p>
            <dl className="data-consent-facts">
              <div><dt>Provider</dt><dd>{text(profile.label) || providerProfile}</dd></div>
              <div><dt>Reasoning</dt><dd>{model || "Auto"}</dd></div>
              <div><dt>Vision</dt><dd>{visionModel && visionModel !== "auto" ? visionModel : text(profile.default_vision_model) || "Unavailable for this provider"}</dd></div>
              <div><dt>Modalities</dt><dd>Tables, signals, arrays, images, and context</dd></div>
              <div><dt>Local only</dt><dd>Raw files and absolute paths never leave this Mac</dd></div>
            </dl>
            <label className="egress-confirm data-egress-confirm">
              <input
                autoFocus={!sessionId}
                type="checkbox"
                checked={confirmDataEgress}
                onChange={(event) => setConfirmDataEgress(event.target.checked)}
              />
              <span>I allow this provider request for this run only.</span>
            </label>
            <label className="data-budget-field">
              <span>Depth</span>
              <select
                value={dataBudget}
                onChange={(event) =>
                  setDataBudget(event.target.value as "fast" | "balanced" | "deep")
                }
              >
                <option value="fast">Fast · 10 min cap</option>
                <option value="balanced">Balanced · 40 min cap</option>
                <option value="deep">Deep · 120 min cap</option>
              </select>
            </label>
            {startDataDiscovery.error ? <p className="field-error" role="alert">{startDataDiscovery.error instanceof Error ? startDataDiscovery.error.message : "Discovery could not start. Please try again."}</p> : null}
            <footer>
              <button
                onClick={() => {
                  setDataConsentOpen(false);
                  setConfirmDataEgress(false);
                }}
              >
                Cancel
              </button>
              <button
                className="primary"
                disabled={!confirmDataEgress || !selectedSources.length || startDataDiscovery.isPending}
                onClick={() => {
                  if (!Boolean(profile.configured)) {
                    setDataConsentOpen(false);
                    setConfirmDataEgress(false);
                    requestProviderSetup();
                    return;
                  }
                  startDataDiscovery.mutate();
                }}
              >
                {startDataDiscovery.isPending ? "Starting…" : "Start discovery"}
              </button>
            </footer>
          </article>
        </div>
      ) : null}

      {isDataProject && !dataStudyId && !canonicalWorkspace.isLoading && mobileSurface === "discovery" ? (
        <section className="data-blank-results">
          <h2>No discovery results yet</h2>
          <p>Your data source is connected. Start discovery to examine its observations and test possible Rules.</p>
          <div><button className="primary" onClick={() => { setConfirmDataEgress(false); setDataConsentOpen(true); }}>Start discovery</button><button onClick={() => { setMobileSurface("map"); setTrayHidden(false); }}>Explore the map</button></div>
        </section>
      ) : null}
      {dataStudyId ? (
        <section
          ref={dataDockRef}
          className={`data-discovery-dock ${dataDockCollapsed ? "collapsed" : ""} ${dataDockExpanded ? "expanded" : ""} ${dataDiscoveryComplete ? "completed" : "running"}`}
          style={
            !dataDockCollapsed && !dataDockExpanded && dataDockSize
              ? { width: dataDockSize.width, height: dataDockSize.height }
              : undefined
          }
          aria-live="polite"
        >
          <header>
            {isDataProject ? <strong className="data-results-heading">Discovery results</strong> : null}
            <div className="data-project-header-copy">
              <small>Local data discovery</small>
              <strong title={projectTitle}>{projectTitle}</strong>
              <p title={projectSummary}>{projectSummary}</p>
            </div>
            <div className="data-study-actions">
              {!isDataProject || dataDockCollapsed ? <button
                aria-label={dataDockCollapsed ? "Expand discovery results" : "Minimize discovery results"}
                aria-expanded={!dataDockCollapsed}
                title={dataDockCollapsed ? "Show discovery results" : "Minimize discovery results"}
                onClick={() => setDataDockCollapsed((current) => !current)}
              >
                {dataDockCollapsed ? "Show" : "Minimize"}
              </button> : null}
              {!dataDockCollapsed && !isDataProject ? (
                <button
                  aria-label={dataDockExpanded ? "Restore discovery results size" : "Expand discovery results workspace"}
                  aria-pressed={dataDockExpanded}
                  title={dataDockExpanded ? "Restore the previous panel size" : "Maximize the discovery workspace"}
                  onClick={() => setDataDockExpanded((current) => !current)}
                >
                  {dataDockExpanded ? "Restore" : "Maximize"}
                </button>
              ) : null}
              <button onClick={() => setDataActivityOpen(true)}>View activity</button>
              <button className="data-action-close" onClick={() => { setDataDockCollapsed(true); if (isDataProject) setMobileSurface("map"); }} aria-label="Close discovery results" title="Close results; discovery continues">×</button>
            </div>
          </header>
          {!dataDockCollapsed ? <div className="data-discovery-scroll">
          {!dataDiscoveryComplete ? <div className="data-discovery-status" role="status">
            <strong>
              {dataStudyLoading
                ? "Restoring saved discovery"
                : activityMessage(dataJob.status_message) || "Saved discovery"}
            </strong>
            <span>
              {dataStudyLoading
                ? "Loading the run receipt"
                : Number(dataExecution.queue_position ?? 0) > 0
                  ? `Queue position ${Number(dataExecution.queue_position)}`
                  : `${humanLabel(text(dataStudy.data?.phase) || "inventory")} · ${dataActivityRows.length} recent receipts`}
            </span>
          </div> : null}
          {!dataDockCollapsed && canonicalRuns.length > 1 ? (
            <label className="data-run-selector">
              <span>Saved run</span>
              <select
                value={dataStudyId}
                onChange={(event) => {
                  setDataStudyId(event.target.value);
                  setSelectedFindingId("");
                  setSelectedRuleId("");
                }}
              >
                {canonicalRuns.map((run, index) => (
                  <option key={text(run.study_id)} value={text(run.study_id)}>
                    Run {canonicalRuns.length - index} · {humanLabel(text(run.state) || "saved")} · {new Date(text(run.created_at) || Date.now()).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {!dataDockCollapsed ? dataStudyLoading ? (
            <div className="data-study-loading" role="status">
              <span className="spinner" aria-hidden="true" />
              <div>
                <strong>Loading the frozen run receipt</strong>
                <p>No analysis is being restarted. Principia is restoring the saved findings, links, and evidence anchors.</p>
              </div>
            </div>
          ) : <>
            <details className="data-run-details"><summary>Run details · {humanLabel(text(dataStudy.data?.state))}{historicalDataRun ? " · Historical evaluation" : ""}</summary>
          {historicalDataRun ? (
            <section className="data-historical-run" role="note">
              <div>
                <strong>Historical run — predates current Rule evaluation</strong>
                <span>Its original evidence is preserved and has not been reconstructed.</span>
              </div>
              <button
                onClick={() => {
                  setConfirmDataEgress(false);
                  setDataConsentOpen(true);
                }}
              >
                Run with current engine
              </button>
            </section>
          ) : null}

            <DataDiscoveryPhases
              phase={text(dataStudy.data?.phase)}
              complete={dataDiscoveryComplete}
              runState={text(dataStudy.data?.state)}
            />
          {dataDiscoveryComplete ? (
            <details className="data-run-trace">
              <summary>
                <span>Run trace</span>
                <small>{dataActivityRows.length} recent events</small>
              </summary>
              <DataActivityFeed events={dataActivityRows} running={false} />
            </details>
          ) : (
            <DataActivityFeed events={dataActivityRows} running />
          )}
          <div className="data-quality-receipt" aria-label="Scientific quality gate">
            <div><strong>{Number(dataCoverage.executed_test_count ?? dataLiveCounts.executed_tests ?? 0)}</strong><span>tests executed</span></div>
            <div><strong>{Number(dataPlanningKnowledge.considered_count ?? rows(dataHypothesisPortfolio.considered_principles).length)}</strong><span>Cloud records grounded</span></div>
            <div><strong>{Math.max(Number(dataScientificProgramExecution.candidate_count ?? 0), dataRuleRows.length + dataRuleCandidateRows.length)}</strong><span>law candidates evaluated</span></div>
            <div><strong>{Number(dataCoverage.surviving_finding_count ?? dataLiveCounts.supported_findings ?? dataFindingRows.length)}</strong><span>supported findings</span></div>
          </div>
          {Number(dataExecution.queue_position ?? 0) > 0 ? (
            <section className="data-queue-receipt" role="status">
              <div>
                <strong>Queued automatically</strong>
                <span>
                  Position {Number(dataExecution.queue_position)} · {Number(dataExecution.active_workers ?? 0)} of {Number(dataExecution.worker_capacity ?? 0)} workers active
                </span>
              </div>
              <p>No data or model request is running for this project yet. Inventory starts as soon as a worker is free.</p>
            </section>
          ) : null}
          {dataDegradedCapabilities.length ? (
            <section className="data-degraded-banner" role="status" aria-label="Reduced capabilities">
              <strong>{dataDiscoveryComplete ? "Completed with reduced capabilities" : "Running with reduced capabilities"}</strong>
              <ul>
                {dataDegradedCapabilities.map((item) => (
                  <li key={`${text(item.capability)}:${text(item.state)}`}>
                    <b>{text(item.capability)}</b> · {text(item.impact)}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {text(dataProviderCapability.state) &&
          text(dataProviderCapability.state) !== "verified" &&
          (text(dataProviderCapability.state) !== "pending" ||
            Number(dataProviderCapability.failed_attempt_count ?? 0) > 0) ? (
            <section className="data-provider-state" role="status">
              <strong>{humanLabel(text(dataProviderCapability.state))}</strong>
              <span>
                {Number(dataProviderCapability.failed_attempt_count ?? 0)} failed remote attempt{Number(dataProviderCapability.failed_attempt_count ?? 0) === 1 ? "" : "s"}
                {text(dataProviderCapability.latest_error_category)
                  ? ` · ${humanLabel(text(dataProviderCapability.latest_error_category))}`
                  : ""}
              </span>
            </section>
          ) : null}
          {text(dataResolvedModels.reasoning_model) ? (
            <p className="data-model-receipt">
              Reasoning model fixed for this run: <strong>{text(dataResolvedModels.reasoning_model)}</strong>
              {text(dataResolvedModels.vision_model)
                ? ` · vision ${text(dataResolvedModels.vision_model)}`
                : " · visual interpretation unavailable"}
            </p>
          ) : null}
          {dataDiscoveryComplete ? (
            <div className="data-study-receipt">
              <span>
                {Number(dataCoverage.surviving_finding_count ?? 0)} survived · {Number(dataCoverage.screened_test_count ?? 0)} tests screened
              </span>
              <a
                href={`/api/v1/data-discoveries/${encodeURIComponent(dataStudyId)}/artifacts/report.md`}
                target="_blank"
                rel="noreferrer"
              >
                Open auditable report
              </a>
              <a
                href={`/api/v1/data-discoveries/${encodeURIComponent(dataStudyId)}/extra-principles/export?format=json`}
                download
              >
                Extra Principles JSON
              </a>
              <a
                href={`/api/v1/data-discoveries/${encodeURIComponent(dataStudyId)}/extra-principles/export?format=md`}
                download
              >
                Extra Principles Markdown
              </a>
            </div>
          ) : null}
          </details>
          <nav aria-label="Data discovery views">
            {(["principles", "observations", "rules", "extra"] as DiscoveryTab[]).map((tab) => (
              <button
                key={tab}
                className={dataTab === tab ? "selected" : ""}
                aria-pressed={dataTab === tab}
                title={
                  tab === "rules" && dataRuleCandidateRows.length
                    ? `${dataRuleRows.length} promoted Rule${dataRuleRows.length === 1 ? "" : "s"}; ${dataRuleCandidateRows.length} additional tested equation candidate${dataRuleCandidateRows.length === 1 ? "" : "s"} held back by scientific gates`
                    : undefined
                }
                onClick={() => setDataTab(tab)}
              >
                <span>{tab[0].toUpperCase() + tab.slice(1)}</span>
                <small>
                  {tab === "principles"
                    ? dataPrincipleFindingRows.length + dataLinkedPrincipleRows.length + dataFoundationRows.length
                    : tab === "observations"
                      ? supportedDataFindingRows.length - dataPrincipleFindingRows.length
                      : tab === "rules"
                        ? dataRuleRows.length
                        : dataExtraPrincipleRows.length}
                  {tab === "rules" && dataRuleCandidateRows.length ? (
                    <em>+{dataRuleCandidateRows.length} tested</em>
                  ) : null}
                </small>
              </button>
            ))}
          </nav>
          <div className="data-discovery-results">
            {dataTab === "principles" && (dataLinkedPrincipleRows.length + dataFoundationRows.length > 0) ? (
              <details className="data-insight-group" open={!dataPrincipleFindingRows.length}>
                <summary>Established background · {dataLinkedPrincipleRows.length + dataFoundationRows.length}</summary>
                <p>Established knowledge linked to this study, including context you add to the map.</p>
                {[...dataLinkedPrincipleRows, ...dataFoundationRows].map((principle) => (
                  <button className="data-finding-card" key={text(principle.id) || text(principle.principle_id)} onClick={() => { closeDataFinding(); setSelectedEdge(null); setSelectedId(text(principle.id) || text(principle.principle_id)); }}>
                    <span className="scientific-badge">{principle.workspace_origin === "user_added" ? "Added by you" : "Established Principle"}</span>
                    <strong><ScientificText value={itemTitle(principle)} /></strong>
                    <p><ScientificText value={text(principle.statement) || text(principle.summary) || text(principle.claim)} /></p>
                  </button>
                ))}
              </details>
            ) : null}
            {dataTab === "principles" ? (
              dataPrincipleFindingRows.length ? (
                <section className="data-insight-group principle_level">
                  <header>
                    <div>
                      <strong>Principle-level results</strong>
                      <p>Scoped, falsifiable principles that survived executed tests and the depth gate.</p>
                    </div>
                    <span>{dataPrincipleFindingRows.length}</span>
                  </header>
                  {dataPrincipleFindingRows.map((finding) => (
                    <button
                      className="data-finding-card principle-result"
                      key={text(finding.finding_id)}
                      onClick={() => openDataFinding(text(finding.finding_id))}
                    >
                      <span className="scientific-badge insight-principle_level">Principle-level result</span>
                      <strong><ScientificText value={text(finding.title)} /></strong>
                      <p><ScientificText value={text(finding.principle_statement) || text(finding.claim)} /></p>
                      {text(finding.practical_value) ? (
                        <span className="data-finding-value"><b>Use</b>{concisePreview(text(finding.practical_value))}</span>
                      ) : null}
                      <small>{text(finding.validation_level).replaceAll("_", " ")} validation · open evidence</small>
                    </button>
                  ))}
                </section>
              ) : (
                <p className="data-empty-state">
                  {dataDiscoveryRunning
                    ? "Principle-level results appear only after executed validation, mechanism, boundary, and falsification checks."
                    : "No result met the Principle-level evidence threshold. Substantive lower-level results remain under Observations; executed equations remain under Rules."}
                </p>
              )
            ) : dataTab === "observations" ? (
              dataObservationGroups.length || screenedDataFindingRows.length || dataNegativeResults.length ? (
                <>
                {dataObservationGroups.map((group) => (
                  <section className={`data-insight-group ${group.level}`} key={group.level}>
                    <header>
                      <div>
                        <strong>{INSIGHT_LABELS[group.level]}</strong>
                        <p>{INSIGHT_DESCRIPTIONS[group.level]}</p>
                      </div>
                      <span>{group.items.length}</span>
                    </header>
                    {group.items.map((finding) => (
                      <button
                        className="data-finding-card"
                        key={text(finding.finding_id)}
                        onClick={() => openDataFinding(text(finding.finding_id))}
                      >
                        <span className={`scientific-badge insight-${group.level}`}>
                          {INSIGHT_LABELS[group.level]}
                        </span>
                        <strong><ScientificText value={text(finding.title)} /></strong>
                        <p><ScientificText value={text(finding.claim)} /></p>
                        {text(finding.practical_value) || text(finding.significance) ? (
                          <span className="data-finding-value">
                            <b>Why it matters</b>
                            {concisePreview(
                              text(finding.practical_value) || text(finding.significance),
                            )}
                          </span>
                        ) : null}
                        <small>
                          {text(finding.validation_level).replaceAll("_", " ")} validation · novelty {text(finding.novelty_status).replaceAll("_", " ")}
                        </small>
                      </button>
                    ))}
                  </section>
                ))}
                {screenedDataFindingRows.length ? (
                  <details className="data-insight-group supporting-evidence">
                    <summary>Additional tests and limitations</summary>
                    <header>
                      <div>
                        <strong>Screened, null & contradicted results</strong>
                        <p>Executed candidates remain inspectable without being presented as supported discoveries.</p>
                      </div>
                      <span>{screenedDataFindingRows.length}</span>
                    </header>
                    {screenedDataFindingRows.map((finding) => (
                      <button
                        className="data-finding-card screened-result"
                        key={text(finding.finding_id)}
                        onClick={() => openDataFinding(text(finding.finding_id))}
                      >
                        <span className="scientific-badge insight-observational">
                          {text(finding.status) === "held_back" ? "Inconclusive" : humanLabel(text(finding.status))}
                        </span>
                        <strong><ScientificText value={text(finding.title)} /></strong>
                        <p>
                          {concisePreview(
                            strings(finding.negative_evidence)[0] ||
                            text(finding.claim),
                            260,
                          )}
                        </p>
                        <small>Open the executed test, diagnostics, and exact evidence anchors</small>
                      </button>
                    ))}
                  </details>
                ) : null}
                {dataNegativeResults.length ? (
                  <details className="data-insight-group supporting-evidence">
                    <summary>Additional tests and limitations</summary>
                    <header>
                      <div>
                        <strong>Additional negative evidence</strong>
                        <p>Test-level diagnostics that are not represented by a standalone finding.</p>
                      </div>
                      <span>{dataNegativeResults.length}</span>
                    </header>
                    <ul className="data-negative-list">
                      {dataNegativeResults.map((item, index) => (
                        <li key={`${index}:${item}`}>{item}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
                </>
              ) : (
                <p className="data-empty-state">
                  {dataDiscoveryRunning
                    ? "Observations appear only after effect-size, robustness, confounder, and evidence-quality checks."
                    : `No observation survived the scientific quality gate. ${Number(dataHypothesisPortfolio.count ?? rows(dataHypothesisPortfolio.hypotheses).length)} domain hypotheses were considered and ${Number(dataCoverage.executed_test_count ?? 0)} executed tests remain in the auditable report.`}
                </p>
              )
            ) : dataTab === "rules" ? (
              <div className="data-rule-list">
                {dataRuleRows.length ? (
                  <section className="data-law-section promoted-laws">
                    <header>
                      <div>
                        <strong>Promoted Rules</strong>
                        <p>{historicalDataRun ? "Historical Rules, preserved under their original evaluation contract." : "Executable law families that passed every declared validation gate."}</p>
                      </div>
                      <span>{dataRuleRows.length}</span>
                    </header>
                    {dataRuleRows.map((rule) => {
                  const headlineMetrics = rows(rule.headline_metrics);
                  const gateSummary = record(rule.gate_summary);
                  const improvement = Number(gateSummary.test_improvement_fraction);
                  return (
                    <button
                      className="data-rule-card"
                      key={text(rule.rule_id)}
                      onClick={() =>
                        openDataFinding(text(rule.finding_id), text(rule.rule_id))
                      }
                    >
                      <span className={`scientific-badge rule-${text(rule.validation_status)}`}>
                        {humanLabel(text(rule.evidence_tier) || text(rule.validation_status))}
                      </span>
                      <small className="data-rule-kind">
                        {humanLabel(text(rule.rule_kind))} · {humanLabel(text(rule.executor_id))}
                      </small>
                      <strong>{text(rule.title)}</strong>
                      <div className="data-rule-equation">
                        <ScientificText value={`$$${text(rule.display_expression_latex) || text(rule.expression_latex)}$$`} />
                      </div>
                      <dl className="data-rule-split">
                        <div><dt>Split</dt><dd>{text(rule.split_strategy).replaceAll("_", " ")}</dd></div>
                        {headlineMetrics.map((metric) => <div key={text(metric.metric_path)}><dt>{text(metric.label)}</dt><dd>{metric.value === null || metric.value === undefined ? "Not measured" : `${Number(metric.value).toPrecision(4)}${text(metric.unit)}`}</dd></div>)}
                        {!headlineMetrics.length ? <div><dt>Evaluation</dt><dd>Open evidence metrics</dd></div> : null}
                      </dl>
                      {Number.isFinite(improvement) ? (
                        <span className="data-rule-improvement">
                          {(improvement * 100).toFixed(1)}% better than the locked baseline
                        </span>
                      ) : null}
                      <p>{concisePreview(text(rule.interpretation), 240)}</p>
                      <small>{Number(rule.calibration_count ?? 1)} calibration{Number(rule.calibration_count ?? 1) === 1 ? "" : "s"} · open gates, residuals, sensitivity, and provenance</small>
                    </button>
                  );
                    })}
                  </section>
                ) : (
                  <p className="data-empty-state">
                    {dataRules.isLoading
                      ? "Restoring executed law families…"
                      : dataDiscoveryRunning
                      ? "Rules appear only after code executes an equation and evaluates it on a separated split."
                      : excludedLegacyEquationCount > 0
                        ? `This historical run contains ${excludedLegacyEquationCount} fitted expression${excludedLegacyEquationCount === 1 ? "" : "s"} without the current split and scientific-gate receipts. They remain in the auditable report, but are not shown as Rules. Run discovery again to evaluate formula-first law families.`
                        : "No equation has completed all Rule checks. Inspect the fitted candidates and the remaining validation work below."}
                  </p>
                )}
                {expressionSearchReceipts.length ? <details className="data-search-receipt">
                  <summary>{expressionCount.toLocaleString()} expressions evaluated · Search coverage</summary>
                  <p>Fitted proposals, held-out candidates, and validated Rules have separate evidence levels.</p>
                  {bindingBlockers.length ? <ul>{bindingBlockers.map(reason => <li key={reason}>{reason}</li>)}</ul> : null}
                </details> : null}
                {dataRuleCandidateRows.length ? (
                  <details className="data-law-section candidate-laws">
                    <summary>Tested law candidates · {dataRuleCandidateRows.length}</summary>
                    <p>Executed equations with failed or unfinished scientific checks. Open a candidate to inspect its evidence and remaining work.</p>
                    {dataRuleCandidateRows.map((candidate) => (
                      <button
                        className="data-rule-card candidate-rule-card"
                        key={text(candidate.candidate_id)}
                        onClick={() =>
                          openDataFinding(
                            text(candidate.finding_id),
                            text(candidate.rule_id),
                          )
                        }
                      >
                        <span className="scientific-badge rule-held_back_candidate">
                          Tested candidate · not a Rule
                        </span>
                        <strong>{text(candidate.title)}</strong>
                        <div className="data-rule-equation">
                          <ScientificText value={`$$${text(candidate.expression_latex)}$$`} />
                        </div>
                        <p>{concisePreview(text(candidate.held_back_reason), 260)}</p>
                        <small>Open the equation, fitted values, gate evidence, and next validation step</small>
                      </button>
                    ))}
                  </details>
                ) : null}
              </div>
            ) : dataTab === "extra" ? (
              <div className="data-linked-principles">
                {dataExtraPrincipleRows.length ? (
                  dataExtraPrincipleRows.map((principle) => (
                    <button
                      key={text(principle.extra_principle_id)}
                      onClick={() => {
                        setSelectedEdge(null);
                        setSelectedId(text(principle.extra_principle_id));
                        setDataDockCollapsed(true);
                      }}
                    >
                      <span className="scientific-badge extra-principle">Extra Principle · provisional</span>
                      <strong>{itemTitle(principle)}</strong>
                      <p>{text(principle.claim)}</p>
                    </button>
                  ))
                ) : (
                  <p className="data-empty-state">No explanatory gap warranted a literature-grounded Extra Principle in this run.</p>
                )}
              </div>
            ) : null}
          </div>
          </> : null}
          {dataResultCollectionsLoading && !dataStudyLoading ? (
            <p className="data-projection-loading" role="status">Restoring remaining evidence records…</p>
          ) : null}
          </div> : null}
          {!dataDockCollapsed && !dataDockExpanded ? (
            <button
              className="data-dock-resize-handle"
              aria-label="Resize discovery results"
              title="Drag to resize"
              onPointerDown={(event) => {
                const bounds = dataDockRef.current?.getBoundingClientRect();
                if (!bounds) return;
                event.preventDefault();
                dataDockResizeRef.current = {
                  pointerId: event.pointerId,
                  x: event.clientX,
                  y: event.clientY,
                  width: bounds.width,
                  height: bounds.height,
                  top: bounds.top,
                };
              }}
            >
              <span aria-hidden="true">⋰</span>
            </button>
          ) : null}
        </section>
      ) : null}

      {dataActivityOpen && dataStudyId ? <DiscoveryActivityDialog
        study={{ ...record(dataStudy.data), ...record(dataStatus.data), coverage: dataCoverage, job: dataJob }} sources={sourceRows} counts={liveStudyCounts}
        cancelling={cancelDataDiscovery.isPending || text(dataJob.state) === "cancelling"}
        error={cancelDataDiscovery.error?.message || (dataStatus.error instanceof Error ? dataStatus.error.message : "")}
        onClose={() => setDataActivityOpen(false)} onStop={() => cancelDataDiscovery.mutate(dataStudyId)}
        onResults={() => { setDataActivityOpen(false); setMobileSurface("discovery"); setDataDockCollapsed(false); }}>
        <DataActivityFeed events={dataActivityRows} running={dataDiscoveryRunning} />
      </DiscoveryActivityDialog> : null}

      {selectedFindingId || selectedRuleId ? createPortal(
        <div
          className="research-modal data-finding-modal"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeDataFinding();
          }}
        >
          <article className="resizable-dialog" ref={findingDialogRef} role="dialog" aria-modal="true" aria-labelledby="data-finding-title" aria-describedby="data-finding-role">
            <header>
              <div>
                <span className={selectedDataRule ? "scientific-badge rule-internally_stable" : "scientific-badge discovery"}>
                  {selectedDataRule
                    ? selectedRuleIsCandidate
                      ? "Tested law candidate · not a Rule"
                      : "Executed symbolic Rule"
                    : "Discovery Finding"}
                </span>
                <h2 id="data-finding-title">
                  {text(selectedDataRule?.title) ||
                    text(selectedDataFinding.data?.title) ||
                    (selectedDataFinding.error ? "Finding unavailable" : "Loading finding…")}
                </h2>
              </div>
              <button ref={findingCloseRef} aria-label="Close finding" onClick={closeDataFinding}>×</button>
            </header>
            <div
              className="data-finding-scroll"
              tabIndex={0}
              aria-label="Scrollable finding and rule details"
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                const viewport = event.currentTarget;
                const page = Math.max(120, viewport.clientHeight * 0.82);
                if (event.key === "PageDown" || event.key === "ArrowDown") {
                  event.preventDefault();
                  viewport.scrollTop += event.key === "ArrowDown" ? 44 : page;
                } else if (event.key === "PageUp" || event.key === "ArrowUp") {
                  event.preventDefault();
                  viewport.scrollTop -= event.key === "ArrowUp" ? 44 : page;
                } else if (event.key === "Home") {
                  event.preventDefault();
                  viewport.scrollTop = 0;
                } else if (event.key === "End") {
                  event.preventDefault();
                  viewport.scrollTop = viewport.scrollHeight;
                }
              }}
            >
              {!selectedDataRule && (selectedScientificLaw.error || selectedDataFinding.error) ? <ErrorState error={selectedScientificLaw.error || selectedDataFinding.error} retry={() => { void selectedDataFinding.refetch(); void selectedScientificLaw.refetch(); }} /> : !selectedDataRule && !selectedDataFinding.data ? <LoadingState label="Loading the scientific record and its evidence…" /> : <>
              {selectedDataRule ? (
                <section className="data-rule-detail">
                  <div className="data-rule-detail-heading">
                    <div>
                      <h3>{selectedRuleIsCandidate ? "Candidate symbolic form" : "General symbolic form"}</h3>
                      <small>
                        {selectedRuleIsCandidate
                          ? "This equation was executed, but it remains outside Rules until every scientific gate passes."
                          : "A reusable equation with calibration and validation available below."}
                      </small>
                    </div>
                    <span className={`scientific-badge rule-${text(selectedDataRule.validation_status)}`}>
                      {humanLabel(text(selectedDataRule.evidence_tier) || text(selectedDataRule.validation_status))}
                    </span>
                  </div>
                  <div className="data-rule-detail-equation">
                    <ScientificText
                      value={`$$${text(selectedDataRule.display_expression_latex) || text(selectedDataRule.expression_latex)}$$`}
                    />
                  </div>
                  <PlainLanguageInterpretation value={record(selectedDataRule.plain_language_interpretation)} fallback={text(selectedDataRule.interpretation)} />
                  <dl className="rule-headline-metrics">{rows(selectedDataRule.headline_metrics).map((metric, index) => <div key={index}><dt>{humanLabel(text(metric.label))}</dt><dd title={String(metric.value)}>{scientificNumber(Number(metric.value))}{text(metric.unit)}</dd></div>)}</dl>
                  <dl className="data-rule-detail-contract">
                    <div>
                      <dt>Rule kind</dt>
                      <dd>{humanLabel(text(selectedDataRule.rule_kind))}</dd>
                    </div>
                    <div>
                      <dt>Model family</dt>
                      <dd>{humanLabel(text(selectedDataRule.rule_family))}</dd>
                    </div>
                    <div>
                      <dt>Validation split</dt>
                      <dd>{humanLabel(text(selectedDataRule.split_strategy))}</dd>
                    </div>
                    <div>
                      <dt>Scope</dt>
                      <dd><ScientificText value={text(selectedDataRule.sample_definition)} /></dd>
                    </div>
                  </dl>
                  <details className="scientific-law-audit rule-symbol-details" open={rows(selectedDisplayCalibration.symbols ?? selectedDataRule.equation_variables).length <= 4 ? true : undefined}>
                  <summary>Variables and input features · {rows(selectedDisplayCalibration.symbols ?? selectedDataRule.equation_variables).length}</summary>
                  <div className="data-rule-symbols">
                    {rows(selectedDisplayCalibration.symbols ?? selectedDataRule.equation_variables).map((variable, index) => (
                      <div key={`${text(variable.symbol)}:${index}`}>
                        <ScientificText value={`$${text(variable.symbol)}$`} />
                        <span title={text(variable.transform)}><ScientificText value={text(variable.meaning)} /></span>
                        {text(variable.unit) ? <small>{text(variable.unit)}</small> : null}
                      </div>
                    ))}
                  </div>
                  </details>
                  <CalibrationDetails display={selectedDisplayCalibration} original={selectedDataRule.parameter_estimates} />
                  <details className="scientific-law-audit"><summary>Development and held-out performance</summary>
                    <ReceiptFields value={{development: selectedDataRule.development, test: selectedDataRule.test, uncertainty: selectedDataRule.uncertainty}} />
                  </details>
                  {selectedRuleIsCandidate ? (
                    <>
                      <h4>Validation status</h4>
                      <p>{text(selectedDataRule.held_back_reason)}</p>
                      <ReceiptFields value={{ failed_gates: selectedDataRule.failed_gates }} />
                    </>
                  ) : null}

                  {Object.keys(selectedLawDetail).length ? (
                    <details className="scientific-law-audit">
                      <summary>Validation gates and calibration details</summary>
                      <div className="scientific-law-detail">
                      <section>
                        <h4>Evidence gates</h4>
                        <ReceiptFields
                          value={{
                            summary: selectedLawDetail.gate_summary,
                            receipts: selectedLawDetail.gate_receipts,
                          }}
                        />
                      </section>
                      {selectedLawCalibrations.map((calibration) => (
                        <section key={text(calibration.calibration_id)}>
                          <h4>{text(calibration.regime) || "Calibration"}</h4>
                          <ReceiptFields
                            value={{
                              development: calibration.development_metrics,
                              validation: calibration.validation_metrics,
                              locked_test: calibration.test_metrics,
                              worst_unit: calibration.worst_unit_metrics,
                              parameter_uncertainty: calibration.parameter_uncertainty,
                              residual_diagnostics: calibration.residual_diagnostics,
                              sensitivity: calibration.sensitivity,
                              support: calibration.support,
                              counterexamples: calibration.counterexamples,
                            }}
                          />
                        </section>
                      ))}
                      {selectedLawEvaluations.length ? (
                        <section>
                          <h4>Locked evaluations</h4>
                          {selectedLawEvaluations.map((evaluation) => (
                            <article className="data-test-receipt" key={text(evaluation.evaluation_id)}>
                              <header>
                                <strong>{humanLabel(text(evaluation.split))}</strong>
                                <span>{evaluation.selection_affected === true ? "selection affected" : "locked"}</span>
                              </header>
                              <ReceiptFields value={{ metrics: evaluation.aggregate_metrics, baseline: evaluation.baseline_metrics, gates: evaluation.gate_results }} />
                            </article>
                          ))}
                        </section>
                      ) : null}
                      {selectedLawFrontier.length ? (
                        <details>
                          <summary>Candidate frontier ({selectedLawFrontier.length})</summary>
                          <div className="law-frontier-list">
                            {selectedLawFrontier.map((candidate) => (
                              <div key={text(candidate.candidate_id)}>
                                <strong>{humanLabel(text(candidate.state))}</strong>
                                <span>complexity {Number(candidate.complexity ?? 0)}</span>
                                <span>development {Number(candidate.development_score ?? 0).toPrecision(4)}</span>
                                <span>validation {Number(candidate.validation_score ?? 0).toPrecision(4)}</span>
                              </div>
                            ))}
                          </div>
                        </details>
                      ) : null}
                      <details>
                        <summary>Executable equation identity</summary>
                        <ReceiptFields value={{ recorded_title: selectedDataRule.recorded_title, executor: selectedDataRule.executor_id, engine: selectedDataRule.engine_version || dataEngineVersion, canonical_ast_digest: selectedLawDetail.canonical_ast_digest, equation_ast: selectedLawDetail.equation_ast, family_digest: selectedLawDetail.family_digest }} />
                      </details>
                      </div>
                    </details>
                  ) : null}
                </section>
              ) : null}
              {selectedDataFinding.data ? <>
              <section className="data-insight-summary"><h3>Scientific role</h3><span className={`scientific-badge insight-${findingInsightLevel(record(selectedDataFinding.data))}`}>{INSIGHT_LABELS[findingInsightLevel(record(selectedDataFinding.data))]}</span><p id="data-finding-role">{INSIGHT_DESCRIPTIONS[findingInsightLevel(record(selectedDataFinding.data))]}</p><p>{text(selectedDataFinding.data?.validation_level).replaceAll("_", " ")} validation · novelty {text(selectedDataFinding.data?.novelty_status).replaceAll("_", " ")}</p><p>{rows(selectedDataFinding.data?.prior_art).length ? `${rows(selectedDataFinding.data?.prior_art).length} prior-art records linked` : "Prior art not assessed"}</p></section>
              <section className="data-scope-summary">
                <h3>Scope and independence</h3>
                {selectedScopeTests.length ? selectedScopeTests.map((test) => (
                  <div key={`scope-${text(test.test_id)}`}>
                    <p>{text(test.sample_definition) || "Sample scope was not recorded."}</p>
                    <span>{Number(test.independent_unit_count ?? 0).toLocaleString()} validation unit{Number(test.independent_unit_count ?? 0) === 1 ? "" : "s"}</span>
                  </div>
                )) : <p>No executed test scope is linked.</p>}
                {selectedScopeRemainder ? <p className="data-scope-more">{selectedScopeRemainder} more executed test{selectedScopeRemainder === 1 ? "" : "s"}; full receipts appear below.</p> : null}
              </section>
              <section><h3>What the data supports</h3><ScientificText value={selectedFindingClaim} /></section>
              {selectedFindingUnexpected ? <section><h3>What is unexpected</h3><ScientificText value={selectedFindingUnexpected} /></section> : null}
              {selectedFindingNontriviality ? <section><h3>Why this is non-trivial</h3><ScientificText value={selectedFindingNontriviality} /></section> : null}
              <PlainLanguageInterpretation title={selectedDataRule ? "Observation context" : "Plain-language interpretation"} value={record(selectedDataFinding.data?.plain_language_interpretation)} fallback={selectedFindingInterpretation} />
              {selectedFindingPracticalValue && !record(selectedDataFinding.data?.plain_language_interpretation).implication ? <section><h3>Why this matters</h3><ScientificText value={selectedFindingPracticalValue} /></section> : null}
              {text(selectedDataFinding.data?.principle_statement) ? <section className="data-principle-statement"><h3>Transferable principle</h3><ScientificText value={text(selectedDataFinding.data?.principle_statement)} /><p><strong>Scope:</strong> {text(selectedDataFinding.data?.transfer_scope)}</p></section> : null}
              {!record(selectedDataFinding.data?.plain_language_interpretation).explanation ? <section><h3>Why it may happen</h3><ScientificText value={text(selectedDataFinding.data?.mechanism)} /></section> : null}
              {strings(selectedDataFinding.data?.principle_ids).length ? (
                <section className="data-explanatory-links">
                  <h3>Explanatory Principles</h3>
                  <div>
                    {strings(selectedDataFinding.data?.principle_ids).map((identifier) => {
                      const principle = linkedPrincipleById.get(identifier) ?? {};
                      return (
                        <button
                          key={identifier}
                          onClick={() => {
                            closeDataFinding();
                            setSelectedEdge(null);
                            setSelectedId(identifier);
                          }}
                        >
                          <span className="scientific-badge">Established Principle</span>
                          <strong>{itemTitle(principle) || "Linked Principle"}</strong>
                          <small>Open full Principle record</small>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ) : null}
              {selectedReasoningChain.length ? <section><h3>Reasoning chain</h3><ol>{selectedReasoningChain.map((item) => <li key={item}>{item}</li>)}</ol></section> : null}
              <section><h3>Robustness and falsification</h3><p>{strings(selectedDataFinding.data?.robustness).join(" · ") || "Not established"}</p><p>{strings(selectedDataFinding.data?.falsifiers).join(" · ")}</p></section>
              <section><h3>Confounders and negative evidence</h3><p>{strings(selectedDataFinding.data?.confounders).join(" · ") || "None recorded"}</p><p>{strings(selectedDataFinding.data?.negative_evidence).join(" · ") || "None recorded"}</p></section>

              <section className="data-receipt-section"><h3>Computed evidence</h3><p>Executed measurements, with sample scope and uncertainty. Values are displayed to four significant digits; full precision is available in each receipt.</p>{selectedFindingTests.length ? selectedFindingTests.map(test => <ComputedEvidence key={text(test.test_id)} test={test} />) : <p>No executed test is linked.</p>}</section>
              <SourceEvidence key={selectedFindingId} evidence={rows(selectedDataFinding.data?.evidence)} />
              {!Object.keys(record(selectedDataFinding.data?.plain_language_interpretation)).length ? <section><h3>Limits and next validation</h3><p>{strings(selectedDataFinding.data?.limits).join(" · ")}</p><p>{text(selectedDataFinding.data?.next_validation)}</p></section> : null}
              </> : selectedDataRule?.finding_pending ? <p className="rule-context-pending" role="status">The equation and its completed tests are available. Scientific context is still being reviewed and will appear here automatically.</p> : null}
              </>}
            </div>
            <footer>
              {record(selectedDataFinding.data?.principle_draft).draft_id ? (
                <span className="scientific-badge data-derived">Principle draft prepared</span>
              ) : selectedDataFinding.data?.promotion_eligible === true ? (
                <button className="primary" disabled={createDataPrincipleDraft.isPending}
                  onClick={() => createDataPrincipleDraft.mutate(selectedFindingId)}>Prepare Principle draft</button>
              ) : null}
              {createDataPrincipleDraft.error ? (
                <p className="field-error" role="alert">
                  {createDataPrincipleDraft.error instanceof Error ? createDataPrincipleDraft.error.message : "The draft could not be prepared."}
                </p>
              ) : null}
            </footer>
            <DialogResizeHandle />
          </article>
        </div>, document.body
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
        isDataProject ? (
          <aside className="research-result-tray data-map-tray">
            <header>
              <div>
                <strong>Study map</strong>
                <small>
                  {dataStudyLoading
                    ? "Restoring saved records…"
                    : `${dataMapTotal} study records and background Principles`}
                </small>
              </div>
              <div className="data-map-header-actions">
                <button
                  className="data-map-add-principle"
                  aria-label="Search and add Global Principles"
                  onClick={() => {
                    setStudio("");
                    closeArtifactDrawer();
                    setGlobalFinderOpen(true);
                  }}
                >
                  ＋ Principle
                </button>
                <button
                  className="research-tray-hide"
                  aria-label="Hide study map records"
                  onClick={() => setTrayHidden(true)}
                >
                  <span>Hide</span>
                  <b>‹</b>
                </button>
              </div>
            </header>
            <nav className="data-map-nav" aria-label="Study map record types">
              {(["principles", "observations", "rules", "extra"] as DataMapTray[]).map((value) => (
                <button
                  key={value}
                  className={dataMapTray === value ? "selected" : ""}
                  onClick={() => setDataMapTray(value)}
                  disabled={dataStudyLoading}
                >
                  <span>{value[0].toUpperCase() + value.slice(1)}</span>
                  <b>{dataMapGroups[value].length}</b>
                </button>
              ))}
            </nav>
            <div className="research-tray-list">
              {dataMapItems.map((item) => (
                <article
                  key={item.principle_id}
                  className={
                    item.record_kind === "meta_principle"
                      ? "meta"
                      : item.record_kind === "discovery_finding"
                        ? "finding"
                        : item.record_kind === "extra_principle"
                          ? "extra"
                          : ""
                  }
                >
                  <button
                    className="tray-preview data-map-preview"
                    onClick={() => {
                      setSelectedEdge(null);
                      if (item.record_kind === "data_rule") {
                        setDataTab("rules");
                        openDataFinding(text(item.payload.finding_id), item.principle_id);
                        return;
                      }
                      if (item.record_kind === "discovery_finding") {
                        setDataTab(findingResultTab(item.payload));
                        openDataFinding(
                          text(item.payload.finding_id) || item.principle_id,
                        );
                        return;
                      }
                      setSelectedId(item.principle_id);
                      setFocusTarget({ id: item.principle_id, request: Date.now() });
                      setDataDockCollapsed(true);
                    }}
                  >
                    <small>
                      {item.record_kind === "meta_principle"
                        ? "Meta foundation"
                        : item.record_kind === "discovery_finding"
                          ? "Discovery finding"
                          : item.record_kind === "data_rule"
                            ? "Evaluated Rule"
                          : item.record_kind === "extra_principle"
                            ? "Extra Principle · provisional"
                            : item.payload.workspace_origin === "user_added" ? "Added by you" : "Established Principle"}
                    </small>
                    <strong><ScientificText value={itemTitle(item.payload)} /></strong>
                    <p><ScientificText value={text(item.payload.claim) || text(item.payload.principle_statement) || text(item.payload.interpretation)} /></p>
                    <span className="data-map-open">Open record</span>
                  </button>
                </article>
              ))}
              {!dataMapItems.length ? (
                <p className="tray-empty" aria-live="polite">
                  {dataStudyLoading || canonicalWorkspace.isLoading
                    ? "Restoring the saved study map…"
                    : dataMapTray === "principles"
                      ? "No Principles are on this map yet. Add background knowledge using + Principle."
                      : `No ${dataMapTray} are linked to this study yet.`}
                </p>
              ) : null}
            </div>
          </aside>
        ) : (
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
                      } catch (error) {
                        setActionNotice(graphSaveMessage(error));
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
                  : "Searching the selected knowledge sources…"}
              </p>
            ) : null}
          </div>
        </aside>
        )
      ) : sessionId ? (
        <button
          className={`show-result-tray${isDataProject ? "" : " manage-principles"}`}
          onClick={() => setTrayHidden(false)}
        >
          {isDataProject ? <>Study map <span>{dataMapTotal}</span></> : "Manage Principles"}
        </button>
      ) : null}

      <main className="research-canvas">
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
              (sessionId ? `${sessionId}:${dataStudyId}` : "") ||
              `global-cloud-atlas:${selectedAtlasAreas.join("|") || "all"}`
            }
            items={graphRows}
            edges={
              sessionId
                ? rows(sessionGraphProjection.edges)
                : rows(cloudAtlas.data?.edges)
            }
            virtualEdges={virtualEdges}
            contextLinks={Boolean(sessionId) && !isDataProject}
            selectedId={selectedId}
            theme={sessionTheme}
            deferViewportUntilInteraction={false}
            initialViewport={sessionId ? savedGraphCamera(persistedViewport) : undefined}
            focusTarget={focusTarget}
            onSelect={(id) => {
              setSelectedEdge(null);
              const graphItem = graphRows.find(
                (item) => item.principle_id === id,
              );
              if (graphItem?.record_kind === "discovery_finding") {
                setDataStudyId(text(graphItem.payload.study_id));
                setDataTab(findingResultTab(graphItem.payload));
                setSelectedRuleId("");
                setSelectedFindingId(id);
                setSelectedId("");
                return;
              }
              if (graphItem?.record_kind === "data_rule") {
                setDataTab("rules");
                openDataFinding(text(graphItem.payload.finding_id), id);
                setSelectedId("");
                return;
              }
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
            onViewport={sessionId ? settleViewport : undefined}
          />
        ) : (
          <div className="research-graph-empty">
            {graph.error || canonicalWorkspace.error ? <><strong>The map could not be loaded</strong><p>Your saved records are preserved.</p><button onClick={() => void (isDataProject ? canonicalWorkspace.refetch() : graph.refetch())}>Retry loading map</button></>
              : sessionId && (isDataProject ? dataDiscoveryRunning || dataStudyLoading || canonicalWorkspace.isLoading : !terminal.has(activeRunState) || session.isLoading || graph.isLoading) ? <><span className="spinner" /><strong>Building your study map</strong><p>{isDataProject ? "Scientific records will appear as their evidence is ready. Follow progress above or open View activity." : "Principles appear automatically when the search results are published."}</p></>
              : sessionId ? <><strong>Your study map is empty</strong><p>{isDataProject ? "Open Results to inspect the completed run, or add background knowledge." : "No Principles were selected for this map. Refine the search or add a Principle."}</p><button onClick={() => setGlobalFinderOpen(true)}>Add Principle</button></>
              : cloudAtlas.error ? <ErrorState error={cloudAtlas.error} retry={() => void cloudAtlas.refetch()} />
              : cloudAtlas.isLoading ? <><span className="spinner" /><strong>Opening the Principles map…</strong></>
              : <><strong>No Principles available</strong><p>Choose another area or check the Cloud snapshot.</p></>}
          </div>
        )}
        <footer className="research-map-footer">
          {sessionId ? (
            <button
              className="research-theme-toggle"
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
          ) : null}
        <div className="research-map-legend" aria-label="Map legend">
          <span>
            <i className="ordinary" />
            Literature Principles
          </span>
          <span>
            <i className="meta" />
            Meta foundations
          </span>
          {sessionId && graphRows.some((item) => item.origin === "virtual_principle" || item.payload.virtual === true) ? (
            <span>
              <i className="virtual" />
              Virtual hypotheses
            </span>
          ) : null}
          {sessionId && graphRows.some((item) => item.record_kind === "discovery_finding") ? (
            <span>
              <i className="finding" />
              Discovery findings
            </span>
          ) : null}
          {sessionId && graphRows.some((item) => item.record_kind === "data_rule") ? (
            <span><i className="rule" />Evaluated Rules</span>
          ) : null}
          {sessionId && graphRows.some((item) => item.record_kind === "extra_principle") ? (
            <span>
              <i className="extra" />
              Extra Principles
            </span>
          ) : null}
          <small>Two-finger move · pinch to zoom</small>
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
            </>
          ) : (
            <span>
              Explore Literature and Meta-Principles together, or enter a
              question above.
            </span>
          )}
        </div>
        </footer>
        {selected ? (
          <FocusDialog resizable title="Principle details" onClose={() => setSelectedId("")}>
          <aside
            className={`research-inspector ${selected.record_kind === "meta_principle" ? "meta" : selected.record_kind === "extra_principle" ? "extra" : ""}`}
            ref={inspectorRef}
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
                    : selected.record_kind === "extra_principle"
                      ? "✦ Extra Principle · provisional research synthesis"
                    : text(selected.payload.area).replaceAll("-", " ")}
                </small>
                <h2>
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
            {selected.record_kind !== "extra_principle" ? <div
              className="principle-metrics"
              title="Reliability reflects review, maturity, evidence, boundary, and falsifiability. Influence reflects this snapshot's evidence and graph connectivity."
            >
              <span>
                <b>{reliabilityScore(selected.payload)}</b> Reliability
              </span>
              <span>
                <b>{influenceScore(selected.payload)}</b> Influence
              </span>
            </div> : <div className="foundation-signature"><span>Status <b>provisional</b></span><span>Cloud <b>not promoted</b></span></div>}
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
                      strings(selected.payload.boundary_conditions).join(" · ") ||
                      text(selected.payload.falsifier) ||
                      strings(selected.payload.falsifiers).join(" · ") ||
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
            {selected.record_kind === "extra_principle" ? (
              <div className="inspector-foundation">
                <strong>Why it was created</strong>
                <p><ScientificText value={text(selected.payload.explanatory_gap)} /></p>
                <strong>Literature basis</strong>
                {rows(selected.payload.supporting_sources).map((source) => (
                  <a key={text(source.source_key)} href={text(source.url) || (text(source.doi) ? `https://doi.org/${text(source.doi)}` : undefined)} target="_blank" rel="noreferrer">
                    {itemTitle(source) || text(source.source_key)}
                  </a>
                ))}
              </div>
            ) : null}
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
              {sessionId && !graphIds.has(selected.principle_id) ? <button onClick={() => void addOrRevealPrinciple({ ...selected.payload, principle_id: selected.principle_id }, false)}>Show on map</button> : null}
              {sessionId && graphIds.has(selected.principle_id) ? (
                <button
                  className="remove-from-graph"
                  onClick={async () => {
                    try {
                      await sendGraphOperations([
                        { action: "remove", principle_id: selected.principle_id },
                      ]);
                    } catch (error) {
                      setActionNotice(graphSaveMessage(error));
                      return;
                    }
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
          </FocusDialog>
        ) : null}
        {selectedEdge ? (
          <FocusDialog resizable title="Connection details" onClose={() => setSelectedEdge(null)}>
          <aside
            className="research-inspector edge"
            ref={inspectorRef}
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
                <small>Connection</small>
                <h2>{selectedEdge.relation_type.replaceAll("_", " ")}</h2>
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
            {selectedEdge.edge_class.endsWith("context") ? (
              <p className="edge-context-note">
                Context edges organize the map for navigation; they are visually
                distinct from reviewed scientific relations.
              </p>
            ) : null}
            </div>
          </aside>
          </FocusDialog>
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
          <aside className="research-modal" role="dialog" aria-modal="true" aria-label="Semantic Cloud search" onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); setGlobalFinderOpen(false); } else trapDialogFocus(event); }}>
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
                <p>{Number(globalFinder.data?.total ?? rows(globalFinder.data?.items).length).toLocaleString()} Principle records found.</p>
              ) : (
                <p>Press Enter or Search to retrieve related Literature and Meta-Principles.</p>
              )}
              {globalFinderMessage ? <p role="status">{globalFinderMessage}</p> : null}
            </div>
            {globalSearchQuery && globalFinder.data ? (
              <div className="global-principle-search-plan">
                <span>
                  {humanLabel(text(record(globalFinder.data.query_plan).intent) || "intersection")} intent
                </span>
                <span>{text(record(globalFinder.data.capabilities).ranking_mode) || "Cloud retrieval"}</span>
                {Boolean(record(globalFinder.data.capabilities).degraded) ? (
                  <span className="warning">Reduced capability</span>
                ) : null}
                {rows(globalFinder.data.supporting_works).slice(0, 2).map((work) => (
                  <p key={text(work.work_id) || itemTitle(work)}>
                    <strong>Bridge provenance:</strong> {itemTitle(work)}
                  </p>
                ))}
              </div>
            ) : null}
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
                        }}
                      >
                        <small>
                          {text(item.principle_class) === "meta"
                            ? "◇ Meta-Principle"
                            : `${humanLabel(text(item.match_section) || "Global Principle")}`}
                        </small>
                        <strong>{itemTitle(item)}</strong>
                        <p>{text(item.claim)}</p>
                        {text(item.match_explanation) ? <p className="match-explanation">{text(item.match_explanation)}</p> : null}
                      </button>
                      <button
                        disabled={addingPrinciples.includes(id)}
                        onClick={() => void addOrRevealPrinciple(item, present)}
                      >
                        {addingPrinciples.includes(id) ? "Adding…" : present ? "Added · show on graph" : "Add to graph"}
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
          {studio === "principle" ? <div className="principle-mode-switch" role="group" aria-label="Principle creation mode">
            <button aria-pressed={principleMode === "ai"} disabled={derivePrinciples.isPending} onClick={() => setPrincipleMode("ai")}>AI Polish</button>
            <button aria-pressed={principleMode === "custom"} disabled={derivePrinciples.isPending} onClick={() => setPrincipleMode("custom")}>Custom</button>
          </div> : null}
          {studio !== "principle" || principleMode === "ai" ? <>
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
          </> : null}
          {studio === "principle" ? <div hidden={principleMode !== "custom"}>
            <CustomPrincipleForm onSave={proposal => saveVirtualLocally(
              { virtual_id: `custom:${crypto.randomUUID()}`, proposal }, 0,
              { provider: "human", model: "custom", trace: { prompt_template: "user-authored" } },
            )} />
          </div> : null}
          {studio !== "principle" || principleMode === "ai" ? <>
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
          {studio === "principle" && generatedPrinciples.map((item, index) => {
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
          </> : null}
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


      </div>
    </div>
  );
}
