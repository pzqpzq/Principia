import { useEffect, useRef, useState } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import {
  stableFoundationOrder,
  stableIdentifierHash,
  stableScaffoldPairs,
} from "./researchGraphTopology";
import {
  graphEdgeLayer,
  type GraphEdgeLayerVisibility,
} from "./researchGraphControls";

export type ResearchGraphItem = {
  principle_id: string;
  record_kind: string;
  origin: string;
  x: number;
  y: number;
  position_source: string;
  z_index: number;
  payload: Record<string, unknown>;
};

type PreparedItem = {
  id: string;
  x: number;
  y: number;
  rank: number;
  title: string;
  area: string;
  isMeta: boolean;
  isArea: boolean;
  isVirtual: boolean;
  payload: Record<string, unknown>;
};

type Move = { principle_id: string; x: number; y: number };
export type ResearchGraphViewport = {
  x: number;
  y: number;
  angle: number;
  ratio: number;
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  zoom: number;
};

export type ResearchGraphEdgeSelection = {
  edge_id: string;
  source_id: string;
  target_id: string;
  edge_class: string;
  relation_type: string;
  rationale: string;
  confidence?: number;
};

type InitialViewport = Partial<Pick<ResearchGraphViewport, "x" | "y" | "angle" | "ratio">>;

// Literature stays in a cool scientific spectrum; Meta-Principles use one
// unmistakable warm foundation color in every theme.
const ordinaryColors = [
  "#4477ff",
  "#00a7c7",
  "#5b72d9",
  "#198f78",
  "#357fb6",
  "#4f69c6",
];
const deepColors = [
  "#7398ff",
  "#22d3ee",
  "#818cf8",
  "#34d399",
  "#60a5fa",
  "#38bdf8",
];
const metaColor = "#f2b84b";
const allEdgeLayers: GraphEdgeLayerVisibility = {
  scientific: true,
  context: true,
  virtual: true,
};

const pairKey = (source: string, target: string) =>
  [source, target].sort().join("\0");

const hash = stableIdentifierHash;

function embeddedLines(
  context: CanvasRenderingContext2D,
  value: string,
  maxWidth: number,
  maxLines: number,
): string[] {
  const words = value.replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (context.measureText(candidate).width <= maxWidth) {
      current = candidate;
      continue;
    }
    if (current) lines.push(current);
    current = word;
    if (lines.length === maxLines) break;
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (lines.length === maxLines && words.join(" ") !== lines.join(" ")) {
    let finalLine = lines[maxLines - 1];
    while (
      finalLine.length > 2 &&
      context.measureText(`${finalLine}…`).width > maxWidth
    )
      finalLine = finalLine.slice(0, -1).trimEnd();
    lines[maxLines - 1] = `${finalLine}…`;
  }
  return lines;
}

function relationRows(item: PreparedItem): Array<Record<string, unknown>> {
  const value = item.payload.relations;
  return Array.isArray(value)
    ? value.filter(
        (entry): entry is Record<string, unknown> =>
          Boolean(entry) && typeof entry === "object",
      )
    : [];
}

export function ResearchGraph({
  items,
  edges = [],
  virtualEdges = [],
  selectedId,
  theme,
  deferViewportUntilInteraction = false,
  initialViewport,
  focusTarget,
  visibleEdgeLayers = allEdgeLayers,
  onSelect,
  onSelectEdge,
  onStageClick,
  onMove,
  onViewport,
}: {
  items: ResearchGraphItem[];
  edges?: Array<Record<string, unknown>>;
  virtualEdges?: Array<Record<string, unknown>>;
  selectedId: string;
  theme: "daylight" | "deep-space";
  deferViewportUntilInteraction?: boolean;
  initialViewport?: InitialViewport;
  focusTarget?: { id: string; request: number } | null;
  visibleEdgeLayers?: GraphEdgeLayerVisibility;
  onSelect: (principleId: string) => void;
  onSelectEdge?: (edge: ResearchGraphEdgeSelection) => void;
  onStageClick?: () => void;
  onMove?: (moves: Move[]) => void;
  onViewport?: (viewport: ResearchGraphViewport) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<Sigma | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const preparedRef = useRef<PreparedItem[]>([]);
  const overviewInitializedRef = useRef(false);
  const detailInitializedRef = useRef(false);
  const handledFocusRef = useRef("");
  const activateViewportRef = useRef<(() => void) | null>(null);
  const localPositionsRef = useRef(new Map<string, { x: number; y: number }>());
  const stableBoundsRef = useRef<{
    x: [number, number];
    y: [number, number];
  } | null>(null);
  const initialViewportRef = useRef(initialViewport);
  initialViewportRef.current = initialViewport;
  const visibleEdgeLayersRef = useRef(visibleEdgeLayers);
  visibleEdgeLayersRef.current = visibleEdgeLayers;
  const [ready, setReady] = useState(false);
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const callbacksRef = useRef({
    onSelect,
    onSelectEdge,
    onStageClick,
    onMove,
    onViewport,
  });
  callbacksRef.current = {
    onSelect,
    onSelectEdge,
    onStageClick,
    onMove,
    onViewport,
  };

  useEffect(() => {
    if (!containerRef.current) return;
    const graph = new Graph({ multi: true, type: "undirected" });
    const renderer = new Sigma(graph, containerRef.current, {
      allowInvalidContainer: true,
      defaultNodeType: "circle",
      defaultEdgeType: "line",
      labelFont: "Inter, ui-sans-serif, system-ui, sans-serif",
      labelWeight: "650",
      labelSize: 12.5,
      labelDensity: 0.42,
      labelGridCellSize: 186,
      labelRenderedSizeThreshold: 1000,
      minCameraRatio: 0.035,
      maxCameraRatio: 14,
      renderEdgeLabels: false,
      enableEdgeEvents: true,
      inertiaDuration: 0,
      inertiaRatio: 1,
      zoomDuration: 0,
      zoomingRatio: 1.22,
      defaultDrawNodeHover: () => undefined,
      zIndex: true,
    });
    renderer.setSetting("edgeReducer", (_edge, data) => ({
      ...data,
      hidden:
        !visibleEdgeLayersRef.current[graphEdgeLayer(data.edge_class)],
    }));
    rendererRef.current = renderer;
    const graphContainer = containerRef.current;
    const titleCanvas = renderer.createCanvas("embedded-titles", {
      beforeLayer: "mouse",
      style: { pointerEvents: "none" },
    });
    const titleContext = titleCanvas.getContext("2d");
    let dragged = "";
    let dragStart = { x: 0, y: 0 };
    let dragDistance = 0;
    let suppressNodeClick = "";
    let suppressClickTimer = 0;
    let cameraTimer = 0;
    let moveTimer = 0;
    let viewportActivated = !deferViewportUntilInteraction;
    activateViewportRef.current = () => {
      viewportActivated = true;
    };
    const pendingMoves = new Map<string, Move>();
    const flushPendingMoves = () => {
      const moves = [...pendingMoves.values()];
      pendingMoves.clear();
      if (moves.length) callbacksRef.current.onMove?.(moves);
    };
    let dragOffset = { x: 0, y: 0 };
    renderer.on("clickNode", ({ node }) => {
      if (suppressNodeClick === node) {
        suppressNodeClick = "";
        return;
      }
      if (node.startsWith("area:")) {
        viewportActivated = true;
        const area = graph.getNodeAttributes(node);
        renderer.getCamera().setState({
          x: Number(area.x),
          y: Number(area.y),
          ratio: renderer.getCamera().getState().ratio / 2.3,
        });
        return;
      }
      callbacksRef.current.onSelect(node);
    });
    renderer.on("clickEdge", ({ edge }) => {
      const [source, target] = graph.extremities(edge);
      const attributes = graph.getEdgeAttributes(edge);
      callbacksRef.current.onSelectEdge?.({
        edge_id: edge,
        source_id: source,
        target_id: target,
        edge_class: String(attributes.edge_class ?? "scientific"),
        relation_type: String(
          attributes.relation_type ??
            attributes.kind ??
            attributes.edge_class ??
            "related",
        ),
        rationale: String(
          attributes.rationale ??
            "This connection is part of the current Principles map.",
        ),
        confidence: Number.isFinite(Number(attributes.confidence))
          ? Number(attributes.confidence)
          : undefined,
      });
    });
    renderer.on("clickStage", () => {
      if (suppressNodeClick) return;
      callbacksRef.current.onSelect("");
      callbacksRef.current.onStageClick?.();
    });
    renderer.on("downNode", ({ node, event }) => {
      viewportActivated = true;
      dragged = node;
      dragStart = { x: Number(event.x), y: Number(event.y) };
      dragDistance = 0;
      const pointer = renderer.viewportToGraph(event);
      const nodePosition = graph.getNodeAttributes(node);
      dragOffset = {
        x: Number(nodePosition.x) - pointer.x,
        y: Number(nodePosition.y) - pointer.y,
      };
      event.preventSigmaDefault();
    });
    const mouse = renderer.getMouseCaptor();
    mouse.on("mousedown", () => {
      viewportActivated = true;
    });
    mouse.on("wheel", () => {
      viewportActivated = true;
    });
    let lastPinchAt = 0;
    let lastPinchMagnitude = 0;
    let lastPinchDirection = 0;
    let pinchDecayFrames = 0;
    let suppressPinchTail = false;
    const handleTrackpadWheel = (event: WheelEvent) => {
      viewportActivated = true;
      event.preventDefault();
      event.stopImmediatePropagation();
      const bounds = graphContainer.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return;
      const unit =
        event.deltaMode === WheelEvent.DOM_DELTA_LINE
          ? 16
          : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
            ? Math.min(bounds.width, bounds.height)
            : 1;
      const state = renderer.getCamera().getState();
      if (event.ctrlKey) {
        const now = performance.now();
        const delta = Math.max(-22, Math.min(22, event.deltaY * unit));
        const magnitude = Math.abs(delta);
        const direction = Math.sign(delta);
        if (now - lastPinchAt > 110) {
          suppressPinchTail = false;
          pinchDecayFrames = 0;
          lastPinchMagnitude = 0;
        }
        if (
          direction === lastPinchDirection &&
          lastPinchMagnitude > 1 &&
          magnitude < lastPinchMagnitude * 0.74
        )
          pinchDecayFrames += 1;
        else if (magnitude >= lastPinchMagnitude * 0.9) pinchDecayFrames = 0;
        if (pinchDecayFrames >= 3 && magnitude < 5) suppressPinchTail = true;
        lastPinchAt = now;
        lastPinchMagnitude = magnitude;
        lastPinchDirection = direction;
        if (suppressPinchTail || magnitude < 0.18) return;
        const nextRatio = Math.max(
          0.035,
          Math.min(14, state.ratio * Math.exp(delta * 0.0062)),
        );
        renderer
          .getCamera()
          .setState(
            renderer.getViewportZoomedState(
              { x: event.clientX - bounds.left, y: event.clientY - bounds.top },
              nextRatio,
            ),
          );
        renderer.scheduleRender();
        return;
      }
      const deltaX = Math.max(-180, Math.min(180, event.deltaX * unit));
      const deltaY = Math.max(-180, Math.min(180, event.deltaY * unit));
      renderer.getCamera().setState({
        ...state,
        x: state.x + (deltaX * state.ratio * 0.82) / bounds.width,
        y: state.y - (deltaY * state.ratio * 0.82) / bounds.height,
      });
      renderer.scheduleRender();
    };
    graphContainer.addEventListener("wheel", handleTrackpadWheel, {
      capture: true,
      passive: false,
    });
    mouse.on("mousemovebody", (event) => {
      if (!dragged) return;
      dragDistance = Math.max(
        dragDistance,
        Math.hypot(Number(event.x) - dragStart.x, Number(event.y) - dragStart.y),
      );
      const pointer = renderer.viewportToGraph(event);
      const position = {
        x: pointer.x + dragOffset.x,
        y: pointer.y + dragOffset.y,
      };
      graph.mergeNodeAttributes(dragged, position);
      localPositionsRef.current.set(dragged, position);
      pendingMoves.set(dragged, { principle_id: dragged, ...position });
      event.preventSigmaDefault();
      event.original.preventDefault();
      renderer.refresh({
        partialGraph: { nodes: [dragged] },
        skipIndexation: true,
        schedule: true,
      });
    });
    mouse.on("mouseup", () => {
      if (!dragged) return;
      const movedNode = dragged;
      dragged = "";
      if (dragDistance > 4) {
        suppressNodeClick = movedNode;
        window.clearTimeout(suppressClickTimer);
        suppressClickTimer = window.setTimeout(() => {
          if (suppressNodeClick === movedNode) suppressNodeClick = "";
        }, 180);
      }
      // Rebuild the picking index once, after the gesture. During movement we
      // deliberately skip it to keep every pointer frame smooth.
      renderer.refresh({
        partialGraph: { nodes: [movedNode] },
        schedule: true,
      });
      window.clearTimeout(moveTimer);
      moveTimer = window.setTimeout(flushPendingMoves, 300);
    });
    let latestCameraState = renderer.getCamera().getState();
    const flushViewport = () => {
      if (!viewportActivated) return;
      const bounds = containerRef.current?.getBoundingClientRect();
      if (!bounds) return;
      const corners = [
        renderer.viewportToGraph({ x: 0, y: 0 }),
        renderer.viewportToGraph({ x: bounds.width, y: 0 }),
        renderer.viewportToGraph({ x: 0, y: bounds.height }),
        renderer.viewportToGraph({ x: bounds.width, y: bounds.height }),
      ];
      callbacksRef.current.onViewport?.({
        ...latestCameraState,
        min_x: Math.min(...corners.map((point) => point.x)),
        max_x: Math.max(...corners.map((point) => point.x)),
        min_y: Math.min(...corners.map((point) => point.y)),
        max_y: Math.max(...corners.map((point) => point.y)),
        zoom: Math.max(0.01, Math.min(100, 1 / latestCameraState.ratio)),
      });
    };
    renderer.getCamera().on("updated", (viewport) => {
      latestCameraState = viewport;
      window.clearTimeout(cameraTimer);
      cameraTimer = window.setTimeout(flushViewport, 750);
      renderer.scheduleRender();
    });
    const titleBuffer = document.createElement("canvas");
    const bufferContext = titleBuffer.getContext("2d");
    const drawEmbeddedTitles = () => {
      if (!titleContext) return;
      const dimensions = renderer.getDimensions();
      const requestedPixelRatio = Math.max(1, window.devicePixelRatio || 1);
      if (
        titleCanvas.width !==
          Math.round(dimensions.width * requestedPixelRatio) ||
        titleCanvas.height !==
          Math.round(dimensions.height * requestedPixelRatio)
      ) {
        titleCanvas.width = Math.round(dimensions.width * requestedPixelRatio);
        titleCanvas.height = Math.round(
          dimensions.height * requestedPixelRatio,
        );
        titleCanvas.style.width = `${dimensions.width}px`;
        titleCanvas.style.height = `${dimensions.height}px`;
      }
      if (!bufferContext) return;
      if (titleBuffer.width !== titleCanvas.width) titleBuffer.width = titleCanvas.width;
      if (titleBuffer.height !== titleCanvas.height) titleBuffer.height = titleCanvas.height;
      const pixelRatio = titleCanvas.width / Math.max(1, dimensions.width);
      bufferContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      bufferContext.clearRect(0, 0, dimensions.width, dimensions.height);
      const ratio = renderer.getCamera().getState().ratio;
      const itemCount = graph.order;
      const titleBudget =
        itemCount <= 160
          ? itemCount
          : ratio < 0.7
            ? 160
            : ratio < 1.7
              ? 112
              : ratio < 3.5
                ? 64
                : 0;
      let renderedTitles = 0;
      for (const edge of graph.edges()) {
        const edgeData = graph.getEdgeAttributes(edge);
        if (String(edgeData.edge_class) !== "virtual") continue;
        if (!visibleEdgeLayersRef.current.virtual) continue;
        const [source, target] = graph.extremities(edge);
        const sourceData = renderer.getNodeDisplayData(source);
        const targetData = renderer.getNodeDisplayData(target);
        if (!sourceData || !targetData || sourceData.hidden || targetData.hidden)
          continue;
        const from = renderer.framedGraphToViewport(sourceData);
        const to = renderer.framedGraphToViewport(targetData);
        bufferContext.save();
        bufferContext.beginPath();
        bufferContext.moveTo(from.x, from.y);
        bufferContext.lineTo(to.x, to.y);
        bufferContext.setLineDash([9, 7]);
        bufferContext.strokeStyle = "rgba(210,98,239,.92)";
        bufferContext.lineWidth = 2.5;
        bufferContext.shadowColor = "rgba(210,98,239,.45)";
        bufferContext.shadowBlur = 5;
        bufferContext.stroke();
        bufferContext.restore();
      }
      for (const node of graph.nodes()) {
        const data = renderer.getNodeDisplayData(node);
        const item = graph.getNodeAttribute(node, "item") as
          | PreparedItem
          | undefined;
        if (!data || !item || data.hidden) continue;
        const position = renderer.framedGraphToViewport(data);
        const radius = renderer.scaleSize(data.size);
        if (
          position.x + radius < 0 ||
          position.y + radius < 0 ||
          position.x - radius > dimensions.width ||
          position.y - radius > dimensions.height
        )
          continue;
        const selected = node === selectedRef.current;
        const canLabel =
          item.isArea ||
          selected ||
          (radius >= (itemCount <= 160 ? 10 : 16) &&
            renderedTitles < titleBudget);

        bufferContext.save();
        bufferContext.beginPath();
        bufferContext.arc(
          position.x,
          position.y,
          radius + (item.isMeta ? 3.5 : 2),
          0,
          Math.PI * 2,
        );
        bufferContext.strokeStyle = selected
          ? "rgba(255,255,255,.98)"
          : item.isMeta
            ? "rgba(255,222,142,.55)"
            : item.isVirtual
              ? "rgba(210,98,239,.94)"
              : "rgba(103,218,255,.38)";
        bufferContext.lineWidth = selected ? 2.6 : item.isMeta ? 1.8 : 1;
        if (item.isVirtual) {
          bufferContext.setLineDash([7, 5]);
          bufferContext.lineWidth = selected ? 3 : 2.2;
        }
        bufferContext.shadowColor = item.isMeta
          ? "rgba(255,208,103,.7)"
          : "rgba(68,164,255,.72)";
        bufferContext.shadowBlur = selected ? 18 : item.isMeta ? 7 : 8;
        bufferContext.stroke();
        if (item.isMeta) {
          bufferContext.beginPath();
          bufferContext.arc(
            position.x,
            position.y,
            radius + 6.5,
            0,
            Math.PI * 2,
          );
          bufferContext.strokeStyle = "rgba(255,232,174,.19)";
          bufferContext.lineWidth = 1;
          bufferContext.stroke();
        }
        bufferContext.restore();
        if (!canLabel) continue;
        renderedTitles += 1;
        const fontSize = Math.max(
          7,
          Math.min(12, radius * (item.isArea ? 0.31 : 0.3)),
        );
        bufferContext.save();
        bufferContext.font = `650 ${fontSize}px Inter, ui-sans-serif, system-ui, sans-serif`;
        bufferContext.textAlign = "center";
        bufferContext.textBaseline = "middle";
        bufferContext.fillStyle = item.isMeta
          ? "rgba(42,29,7,.96)"
          : "rgba(255,255,255,.96)";
        bufferContext.shadowColor = item.isMeta
          ? "rgba(255,247,220,.55)"
          : "rgba(1,8,20,.82)";
        bufferContext.shadowBlur = item.isMeta ? 0.6 : 3;
        const title = item.isMeta ? `◇ ${item.title}` : item.title;
        const lines = embeddedLines(
          bufferContext,
          title,
          Math.max(16, radius * 1.46),
          radius >= 28 ? 3 : 2,
        );
        const lineHeight = fontSize * 1.05;
        const startY = position.y - ((lines.length - 1) * lineHeight) / 2;
        lines.forEach((line, index) =>
          bufferContext.fillText(line, position.x, startY + index * lineHeight),
        );
        bufferContext.restore();
      }
      // Swap the completed frame in one paint. Clearing and redrawing the
      // visible canvas directly exposed a blank frame when an inspector was
      // dismissed, which looked like the entire graph flashing.
      titleContext.setTransform(1, 0, 0, 1, 0, 0);
      titleContext.clearRect(0, 0, titleCanvas.width, titleCanvas.height);
      titleContext.drawImage(titleBuffer, 0, 0);
    };
    renderer.on("afterRender", drawEmbeddedTitles);
    return () => {
      window.clearTimeout(cameraTimer);
      window.clearTimeout(moveTimer);
      window.clearTimeout(suppressClickTimer);
      flushPendingMoves();
      flushViewport();
      graphContainer.removeEventListener("wheel", handleTrackpadWheel, {
        capture: true,
      });
      renderer.off("afterRender", drawEmbeddedTitles);
      renderer.kill();
      rendererRef.current = null;
      activateViewportRef.current = null;
    };
  }, []);

  useEffect(() => {
    workerRef.current?.terminate();
    const worker = new Worker(
      new URL("./graphTile.worker.ts", import.meta.url),
      { type: "module" },
    );
    workerRef.current = worker;
    worker.onmessage = (event: MessageEvent<{ items: PreparedItem[] }>) => {
      preparedRef.current = event.data.items;
      setReady(true);
      const renderer = rendererRef.current;
      if (!renderer) return;
      const graph = renderer.getGraph();
      if (event.data.items.length) {
        const nextBounds = {
          x: [Math.min(...event.data.items.map((item) => item.x)), Math.max(...event.data.items.map((item) => item.x))] as [number, number],
          y: [Math.min(...event.data.items.map((item) => item.y)), Math.max(...event.data.items.map((item) => item.y))] as [number, number],
        };
        // Freeze the world normalization after the first lightweight tile.
        // Expanding or shrinking this box when later viewport tiles arrive
        // makes the same camera state point at a different place, which feels
        // like zoom inertia or a sudden jump to the user.
        if (!stableBoundsRef.current) stableBoundsRef.current = nextBounds;
        else {
          // Membership additions may extend the map, but refreshes and drags
          // never shrink or renormalize the existing world.
          stableBoundsRef.current = {
            x: [
              Math.min(stableBoundsRef.current.x[0], nextBounds.x[0]),
              Math.max(stableBoundsRef.current.x[1], nextBounds.x[1]),
            ],
            y: [
              Math.min(stableBoundsRef.current.y[0], nextBounds.y[0]),
              Math.max(stableBoundsRef.current.y[1], nextBounds.y[1]),
            ],
          };
        }
        const bounds = stableBoundsRef.current;
        const paddingX = Math.max(1, (bounds.x[1] - bounds.x[0]) * 0.08);
        const paddingY = Math.max(1, (bounds.y[1] - bounds.y[0]) * 0.08);
        renderer.setCustomBBox({
          x: [bounds.x[0] - paddingX, bounds.x[1] + paddingX],
          y: [bounds.y[0] - paddingY, bounds.y[1] + paddingY],
        });
      }
      graph.clear();
      const palette = theme === "deep-space" ? deepColors : ordinaryColors;
      const overviewTile =
        event.data.items.length > 0 &&
        event.data.items.every((entry) => entry.isArea);
      for (const item of event.data.items) {
        const localPosition = localPositionsRef.current.get(item.id);
        graph.addNode(item.id, {
          x: localPosition?.x ?? item.x,
          y: localPosition?.y ?? item.y,
          label: null,
          color: item.isArea
            ? palette[hash(item.area) % palette.length]
            : item.isMeta
              ? metaColor
              : item.isVirtual
                ? "#c866e4"
              : palette[hash(item.id) % palette.length],
          size: item.isArea
            ? 30 +
              Math.min(
                18,
                Math.sqrt(Number(item.payload.principle_count ?? 1)) * 1.25,
              )
            : item.isMeta
              ? 32
              : 42,
          zIndex: item.isArea ? 6 : item.isMeta ? 4 : 2,
          item,
          highlighted: false,
        });
      }
      const ids = new Set(event.data.items.map((item) => item.id));
      const seen = new Set<string>();
      if (overviewTile) {
        const areaItems = event.data.items.filter((item) => item.isArea);
        for (let index = 0; index < areaItems.length; index += 1) {
          const source = areaItems[index].id;
          const target = areaItems[(index + 1) % areaItems.length].id;
          graph.addEdgeWithKey(`area-overview:${index}`, source, target, {
            color:
              theme === "deep-space"
                ? "rgba(96,144,255,.52)"
                : "rgba(56,166,214,.5)",
            size: 1.8,
            zIndex: 0,
            edge_class: "area_overview",
            relation_type: "area proximity",
            rationale:
              "This overview connection keeps neighboring scientific areas legible at world scale.",
          });
        }
      }
      for (const relation of edges) {
        const source = String(
          relation.source ?? relation.source_principle_id ?? "",
        );
        const target = String(
          relation.target ?? relation.target_principle_id ?? "",
        );
        if (!ids.has(source) || !ids.has(target) || source === target) continue;
        const key = [source, target].sort().join("\0");
        if (seen.has(key)) continue;
        seen.add(key);
        const edgeClass = String(relation.edge_class ?? "validated");
        graph.addEdgeWithKey(
          `snapshot:${String(relation.edge_id ?? relation.relation_id ?? key)}`,
          source,
          target,
          {
            ...relation,
            edge_class: edgeClass,
            color:
              edgeClass === "foundation"
                ? "rgba(255,210,114,.86)"
                : theme === "deep-space"
                  ? "rgba(117,145,255,.58)"
                  : "rgba(72,184,230,.58)",
            size: edgeClass === "foundation" ? 3.1 : 1.9,
            zIndex: edgeClass === "foundation" ? 2 : 1,
          },
        );
      }
      for (const item of event.data.items) {
        for (const relation of relationRows(item)) {
          const source = String(
            relation.source_principle_id ?? relation.source ?? "",
          );
          const target = String(
            relation.target_principle_id ?? relation.target ?? "",
          );
          if (!ids.has(source) || !ids.has(target) || source === target)
            continue;
          const key = [source, target].sort().join("\0");
          if (seen.has(key)) continue;
          seen.add(key);
          graph.addEdgeWithKey(`relation:${key}`, source, target, {
            ...relation,
            edge_class: String(relation.edge_class ?? "validated"),
            color:
              theme === "deep-space"
                ? "rgba(117,145,255,.58)"
                : "rgba(72,184,230,.58)",
            size: 1.9,
            zIndex: 1,
          });
        }
      }
      for (const relation of virtualEdges) {
        const source = String(
          relation.source ?? relation.source_principle_id ?? "",
        );
        const target = String(
          relation.target ?? relation.target_principle_id ?? "",
        );
        if (!ids.has(source) || !ids.has(target) || source === target) continue;
        const key = [source, target].sort().join("\0");
        if (seen.has(key)) continue;
        seen.add(key);
        graph.addEdgeWithKey(
          `virtual:${String(relation.relation_id ?? key)}`,
          source,
          target,
          {
            ...relation,
            color: "rgba(0,0,0,0)",
            size: 5.4,
            zIndex: 3,
            edge_class: "virtual",
            relation_type: String(
              relation.relation_type ?? relation.kind ?? "derived connection",
            ),
            rationale: String(
              relation.rationale ??
                "This connection was derived in the current research session.",
            ),
          },
        );
      }
      // Add a clearly styled cross-class scaffold so literature and its nearby
      // foundations do not read as two disconnected galaxies. These are
      // visual semantic-context links; validated FoundationLinks above remain
      // thicker and take precedence whenever both endpoints are present.
      const literatureItems = event.data.items.filter(
        (item) => !item.isArea && !item.isMeta,
      );
      const metaItems = event.data.items.filter((item) => item.isMeta);
      const metaDegree = new Map<string, number>();
      for (const literature of literatureItems) {
        const sameArea = metaItems.filter(
          (candidate) => candidate.area === literature.area,
        );
        const candidates = sameArea.length ? sameArea : metaItems;
        const eligible = candidates.filter(
          (candidate) =>
            (metaDegree.get(candidate.id) ?? 0) <
            (event.data.items.length <= 40 ? 4 : 5),
        );
        const targetId = stableFoundationOrder(
          literature.id,
          eligible.map((candidate) => candidate.id),
        )[0];
        const target = eligible.find((candidate) => candidate.id === targetId);
        if (!target) continue;
        const key = [literature.id, target.id].sort().join("\0");
        if (seen.has(key)) continue;
        seen.add(key);
        metaDegree.set(target.id, (metaDegree.get(target.id) ?? 0) + 1);
        graph.addEdgeWithKey(
          `foundation-context:${literature.id}:${target.id}`,
          literature.id,
          target.id,
          {
            color: "rgba(242,184,75,.58)",
            size: 1.65,
            zIndex: 1,
            edge_class: "foundation_context",
            relation_type: "semantic foundation context",
            rationale:
              "A visual context link between a literature Principle and a nearby Meta-Principle candidate; it is distinct from a reviewed FoundationLink.",
          },
        );
      }
      // Keep sparse corpora legible without an all-pairs pass: neighboring
      // records inside each stable area receive at most two context edges.
      const byArea = new Map<string, PreparedItem[]>();
      for (const item of event.data.items)
        byArea.set(item.area, [...(byArea.get(item.area) ?? []), item]);
      for (const [area, group] of byArea) {
        const principles = group.filter((item) => !item.isArea);
        principles.sort(
          (left, right) =>
            left.rank - right.rank || left.id.localeCompare(right.id),
        );
        for (let index = 1; index < principles.length; index += 1) {
          const source = principles[index - 1].id;
          const target = principles[index].id;
          const key = [source, target].sort().join("\0");
          if (seen.has(key)) continue;
          seen.add(key);
          graph.addEdgeWithKey(`area:${area}:${index}`, source, target, {
            color:
              theme === "deep-space"
                ? "rgba(91,142,235,.58)"
                : "rgba(67,185,226,.56)",
            size: 1.35,
            zIndex: 0,
            edge_class: "area_context",
            relation_type: "area context",
            rationale: `These Principles share the ${area.replaceAll("-", " ")} scientific area.`,
          });
        }
      }
      if (event.data.items.length > 40) {
        const clusters = [...byArea.entries()]
          .map(([area, group]) => {
            const members = group
              .filter((item) => !item.isArea)
              .sort(
                (left, right) =>
                  left.rank - right.rank || left.id.localeCompare(right.id),
              );
            return { area, members };
          })
          .filter((cluster) => cluster.members.length)
          .sort((left, right) => left.area.localeCompare(right.area));
        const clusterEdges = new Set<string>();
        for (let index = 0; index < clusters.length; index += 1) {
          const cluster = clusters[index];
          const nearest = clusters[(index + 1) % clusters.length];
          if (!nearest || nearest.area === cluster.area) continue;
          const source = cluster.members[0].id;
          const target = nearest.members[0].id;
          const key = [source, target].sort().join("\0");
          if (seen.has(key) || clusterEdges.has(key)) continue;
          seen.add(key);
          clusterEdges.add(key);
          graph.addEdgeWithKey(
            `cluster:${cluster.area}:${nearest.area}`,
            source,
            target,
            {
              color:
                theme === "deep-space"
                  ? "rgba(108,160,255,.67)"
                  : "rgba(75,198,240,.65)",
              size: 1.55,
              zIndex: 0,
              edge_class: "cluster_context",
              relation_type: "cross-area context",
              rationale:
                "A visual navigation link between neighboring scientific clusters.",
            },
          );
        }
      }
      // A stable, near-linear scaffold keeps sparse and cross-disciplinary
      // maps legible without turning visual coordinates into scientific
      // meaning. Node dragging therefore never changes graph topology.
      const scaffold = event.data.items
        .filter((item) => !item.isArea)
        .map((item) => item.id);
      for (const [source, target] of stableScaffoldPairs(scaffold, seen)) {
        const key = pairKey(source, target);
        seen.add(key);
        graph.addEdgeWithKey(`scaffold:${source}:${target}`, source, target, {
          color:
            theme === "deep-space"
              ? "rgba(82,132,220,.48)"
              : "rgba(56,165,211,.46)",
          size: 1.15,
          zIndex: 0,
          edge_class: "context_scaffold",
          relation_type: "map context",
          rationale:
            "A stable visual navigation link; moving nodes never changes this topology.",
        });
      }
      renderer.setSetting("nodeReducer", (node, data) => {
        const ratio = renderer.getCamera().getState().ratio;
        const item = graph.getNodeAttribute(node, "item") as PreparedItem;
        // The server deliberately returns only area supernodes for the first,
        // world-scale tile. Sigma starts at ratio 1, so infer the overview from
        // the tile contents instead of hiding every area until the user zooms.
        const areaOverview = overviewTile;
        const densityScale =
          graph.order > 180
            ? 0.54
            : graph.order > 60
              ? 0.65
              : graph.order <= 40
                ? 1.25
                : 1;
        return {
          ...data,
          hidden: areaOverview ? !item.isArea : item.isArea,
          label: null,
          size:
            (ratio > 4 ? Math.max(9, data.size * 0.82) : data.size) *
            densityScale,
          color:
            node === selectedRef.current
              ? item.isMeta
                ? "#ffd778"
                : "#8cdcff"
              : data.color,
          highlighted: false,
        };
      });
      if (overviewTile && !overviewInitializedRef.current) {
        overviewInitializedRef.current = true;
        renderer.getCamera().setState({ x: 0.5, y: 0.5, ratio: 1.55 });
      } else if (
        !deferViewportUntilInteraction &&
        !overviewTile &&
        event.data.items.length <= 40 &&
        !detailInitializedRef.current
      ) {
        detailInitializedRef.current = true;
        // Small research sessions should read as one compact constellation:
        // pull the coordinates inward on screen while enlarging their cards.
        const saved = initialViewportRef.current;
        const savedRatio = Number(saved?.ratio ?? 0.9);
        const savedX = Number(saved?.x ?? 0.5);
        const savedY = Number(saved?.y ?? 0.5);
        const refitLegacyViewport =
          savedRatio > 1.12 ||
          (!Number.isFinite(savedX) || !Number.isFinite(savedY)) ||
          (Math.abs(savedX) < 0.01 && Math.abs(savedY) < 0.01);
        renderer.getCamera().setState({
          x: refitLegacyViewport ? 0.5 : savedX,
          y: refitLegacyViewport ? 0.5 : savedY,
          angle: Number(saved?.angle ?? 0),
          ratio: Math.min(savedRatio, 0.92),
        });
      }
      renderer.refresh();
    };
    worker.postMessage({
      items,
      includeAreaSupernodes: deferViewportUntilInteraction,
    });
    return () => worker.terminate();
  }, [items, edges, theme, virtualEdges]);

  useEffect(() => {
    rendererRef.current?.scheduleRender();
  }, [selectedId]);

  useEffect(() => {
    rendererRef.current?.refresh({ skipIndexation: true, schedule: true });
  }, [
    visibleEdgeLayers.scientific,
    visibleEdgeLayers.context,
    visibleEdgeLayers.virtual,
  ]);

  useEffect(() => {
    if (!focusTarget?.id) return;
    const focusKey = `${focusTarget.id}:${focusTarget.request}`;
    if (handledFocusRef.current === focusKey) return;
    let frame = 0;
    let attempts = 0;
    const focusWhenReady = () => {
      if (handledFocusRef.current === focusKey) return;
      const renderer = rendererRef.current;
      const graph = renderer?.getGraph();
      if (renderer && graph?.hasNode(focusTarget.id)) {
        const data = renderer.getNodeDisplayData(focusTarget.id);
        if (data) {
          const current = renderer.getCamera().getState();
          renderer.getCamera().setState({
            ...current,
            x: data.x,
            y: data.y,
            ratio: Math.min(current.ratio, 0.82),
          });
          renderer.scheduleRender();
          handledFocusRef.current = focusKey;
          return;
        }
      }
      attempts += 1;
      if (attempts < 45) frame = window.requestAnimationFrame(focusWhenReady);
    };
    focusWhenReady();
    return () => window.cancelAnimationFrame(frame);
  }, [focusTarget?.id, focusTarget?.request, items]);

  const zoom = (direction: "in" | "out") => {
    const renderer = rendererRef.current;
    if (!renderer) return;
    activateViewportRef.current?.();
    const camera = renderer.getCamera();
    const current = camera.getState();
    const ratio = Math.max(
      0.035,
      Math.min(14, current.ratio * (direction === "in" ? 0.72 : 1.38)),
    );
    camera.setState({ ...current, ratio });
  };

  return (
    <div
      className={`research-graph sigma-${theme}`}
      role="application"
      aria-label="Interactive Principles graph"
    >
      <div className="research-graph-stage" ref={containerRef} />
      <div className="research-graph-zoom" aria-label="Graph size controls">
        <button
          type="button"
          onClick={() => zoom("in")}
          aria-label="Make graph larger"
          title="Zoom in"
        >
          ＋
        </button>
        <button
          type="button"
          onClick={() => zoom("out")}
          aria-label="Make graph smaller"
          title="Zoom out"
        >
          −
        </button>
      </div>
      {!ready ? (
        <div className="research-graph-preparing" aria-live="polite">
          <span className="spinner" />
          <strong>Preparing the Principles map…</strong>
          <small>Loading a lightweight overview first</small>
        </div>
      ) : null}
    </div>
  );
}
