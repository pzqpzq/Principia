import { memo, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Panel,
  PanOnScrollMode,
  Position,
  ReactFlow,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import type { components } from "../api/schema";

type PrincipleCard = components["schemas"]["PrincipleCardResponse"];
type PrincipleEdge = components["schemas"]["PrincipleGraphEdgeResponse"];
type PotentialRelation = components["schemas"]["PotentialRelationResponse"];
type PotentialRelationsResponse = components["schemas"]["PotentialRelationsResponse"];
type VirtualGenerationResponse = components["schemas"]["VirtualPrincipleGenerationResponse"];
type GeneratedVirtualPrinciple = components["schemas"]["GeneratedVirtualPrinciple"];
type VirtualPrincipleProposal = components["schemas"]["VirtualPrincipleProposal"];
type PrincipleNodeData = { card: PrincipleCard; isolated: boolean };
type PrincipleNode = Node<PrincipleNodeData, "principle">;
type GraphRelationData = {
  virtual: boolean;
  relation: PrincipleEdge | PotentialRelation;
  edgeClass: string;
};
type GraphTheme = "macaron" | "midnight";
type VirtualConnectionBatch = {
  batchId: string;
  createdAt: number;
  principleIds: string[];
  relations: PotentialRelation[];
};
type VirtualPrincipleBatch = {
  batchId: string;
  createdAt: number;
  principleIds: string[];
  researchDirection: string;
  generation: VirtualGenerationResponse;
  items: GeneratedVirtualPrinciple[];
};
type ArtifactTrayView = "" | "connections" | "principles";

type ProviderChoice = { provider: string; label: string; configured: boolean; defaultModel: string; models: string[] };

const WIDTH = 348;
const HEIGHT = 226;
const reasoningStages = [
  { title: "Reading the selected Principles", detail: "Comparing claims, scopes, conditions, and boundaries." },
  { title: "Mapping mechanisms", detail: "Looking for complementary causal and structural building blocks." },
  { title: "Testing boundary combinations", detail: "Checking where a synthesis may fail or become conditional." },
  { title: "Balancing reliability and novelty", detail: "Separating plausible extensions from genuinely new hypotheses." },
  { title: "Writing falsifiable Principles", detail: "Producing concise claims with explicit tests and limitations." },
];

function sessionBatchId(prefix: string): string {
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`;
}

const midnightRelationColors: Record<string, string> = {
  supports: "#258164",
  contradicts: "#c65462",
  refines: "#3978b8",
  generalizes: "#6b55d9",
  specializes: "#92703a",
  depends_on: "#537589",
  analogous_to: "#8b5aad",
};
const macaronRelationColors: Record<string, string> = {
  supports: "#4f9a7d",
  contradicts: "#d96f80",
  refines: "#5c83bd",
  generalizes: "#7a69c6",
  specializes: "#a57a45",
  depends_on: "#66889a",
  analogous_to: "#a0649e",
};

function readableRelation(value: string): string {
  return value.replace(/^potential_/, "potential ").replaceAll("_", " ");
}

const PrincipleNodeCard = memo(function PrincipleNodeCard({ data }: NodeProps<PrincipleNode>) {
  const { card } = data;
  const reliability = card.reliability_score ?? 0;
  const influence = card.influence_score ?? 0;
  return <>
    {[Position.Top, Position.Right, Position.Bottom, Position.Left].flatMap((position) => [
      <Handle key={`source-${position}`} id={`source-${position}`} type="source" position={position} isConnectable={false} />,
      <Handle key={`target-${position}`} id={`target-${position}`} type="target" position={position} isConnectable={false} />,
    ])}
    <div className="principle-graph-node-content">
      <div className="principle-graph-node-meta"><span>{card.virtual ? "Virtual hypothesis" : card.source === "local" ? "Local" : card.source === "both" ? "Global + Local" : "Global"}</span><span>{card.supporting_work_count} paper{card.supporting_work_count === 1 ? "" : "s"}</span></div>
      <strong>{card.title}</strong>
      <p>{card.claim}</p>
      <small>{card.area_labels.length ? card.area_labels.slice(0, 2).map((area) => area.replaceAll("-", " ")).join(" · ") : "Not categorized"}</small>
      <div className="principle-graph-node-metrics"><span><i style={{ width: `${reliability}%` }} /><b>Reliability</b><em>{Math.round(reliability)}</em></span><span><i style={{ width: `${influence}%` }} /><b>Influence</b><em>{card.influence_score == null ? "—" : Math.round(influence)}</em></span></div>
    </div>
  </>;
});

const nodeTypes = { principle: PrincipleNodeCard };

function connectedComponents(ids: string[], adjacency: Map<string, Set<string>>): string[][] {
  const remaining = new Set(ids.filter((id) => (adjacency.get(id)?.size ?? 0) > 0));
  const components: string[][] = [];
  while (remaining.size) {
    const start = [...remaining].sort()[0];
    const queue = [start];
    const component: string[] = [];
    remaining.delete(start);
    while (queue.length) {
      const current = queue.shift()!;
      component.push(current);
      [...(adjacency.get(current) ?? [])].sort().forEach((neighbor) => {
        if (remaining.delete(neighbor)) queue.push(neighbor);
      });
    }
    components.push(component.sort((left, right) => {
      const degree = (adjacency.get(right)?.size ?? 0) - (adjacency.get(left)?.size ?? 0);
      return degree || left.localeCompare(right);
    }));
  }
  return components.sort((left, right) => right.length - left.length || left[0].localeCompare(right[0]));
}

function layoutPrinciples(cards: PrincipleCard[], relations: PrincipleEdge[]): PrincipleNode[] {
  const ordered = [...cards].sort((left, right) => left.id.localeCompare(right.id));
  const cardById = new Map(ordered.map((card) => [card.id, card]));
  const adjacency = new Map(ordered.map((card) => [card.id, new Set<string>()]));
  relations.forEach((relation) => {
    if (!adjacency.has(relation.source) || !adjacency.has(relation.target)) return;
    adjacency.get(relation.source)!.add(relation.target);
    adjacency.get(relation.target)!.add(relation.source);
  });
  const components = connectedComponents(ordered.map((card) => card.id), adjacency);
  const positions = new Map<string, { x: number; y: number }>();
  let nextComponentCenterX = 620;
  components.forEach((component, componentIndex) => {
    const center = { x: nextComponentCenterX, y: 540 };
    positions.set(component[0], center);
    let cursor = 1;
    let ring = 0;
    let outerRadius = 0;
    while (cursor < component.length) {
      const radius = 520 + ring * 400;
      const capacity = Math.max(6, Math.floor((2 * Math.PI * radius) / (WIDTH + 96)));
      const count = Math.min(capacity, component.length - cursor);
      for (let index = 0; index < count; index += 1) {
        const angle = -Math.PI / 2 + componentIndex * 0.29 + (2 * Math.PI * index) / count;
        positions.set(component[cursor + index], {
          x: center.x + Math.cos(angle) * radius,
          y: center.y + Math.sin(angle) * radius,
        });
      }
      cursor += count;
      outerRadius = radius;
      ring += 1;
    }
    nextComponentCenterX += Math.max(1_180, outerRadius * 2 + WIDTH + 620);
  });

  const connectedIds = components.flat();

  const isolates = ordered.filter((card) => !positions.has(card.id));
  const connectedMaximumX = connectedIds.length
    ? Math.max(...connectedIds.map((id) => positions.get(id)!.x))
    : -260;
  const isolateStartX = Math.max(320, connectedMaximumX + 520);
  const isolateColumns = isolates.length > 8 ? 3 : isolates.length > 3 ? 2 : 1;
  isolates.forEach((card, index) => positions.set(card.id, {
    x: isolateStartX + (index % isolateColumns) * (WIDTH + 52),
    y: 190 + Math.floor(index / isolateColumns) * (HEIGHT + 44),
  }));

  return ordered.map((card) => {
    const center = positions.get(card.id)!;
    const isolated = (adjacency.get(card.id)?.size ?? 0) === 0;
    return {
      id: card.id,
      type: "principle",
      position: { x: center.x - WIDTH / 2, y: center.y - HEIGHT / 2 },
      className: `principle-graph-node ${card.source}${isolated ? " isolated" : ""}`,
      style: { width: WIDTH, height: HEIGHT },
      ariaLabel: `${card.title}. ${card.supporting_work_count} supporting papers.${isolated ? " No validated relation in this view." : ""}`,
      data: { card, isolated },
    };
  });
}

function routeHandles(source: PrincipleNode | undefined, target: PrincipleNode | undefined) {
  if (!source || !target) return { sourceHandle: "source-right", targetHandle: "target-left" };
  const sourceX = source.position.x + WIDTH / 2;
  const sourceY = source.position.y + HEIGHT / 2;
  const targetX = target.position.x + WIDTH / 2;
  const targetY = target.position.y + HEIGHT / 2;
  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0
    ? { sourceHandle: "source-right", targetHandle: "target-left" }
    : { sourceHandle: "source-left", targetHandle: "target-right" };
  return dy >= 0
    ? { sourceHandle: "source-bottom", targetHandle: "target-top" }
    : { sourceHandle: "source-top", targetHandle: "target-bottom" };
}

function graphEdges(
  relations: PrincipleEdge[],
  virtualRelations: PotentialRelation[],
  nodes: PrincipleNode[],
  showLabels: boolean,
  theme: GraphTheme,
): Edge<GraphRelationData>[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const relationColors = theme === "macaron" ? macaronRelationColors : midnightRelationColors;
  const labelBackground = theme === "macaron" ? "#fffdfa" : "#13182a";
  const validated = relations.map((relation): Edge<GraphRelationData> => {
    const edgeClass = relation.edge_class ?? "validated";
    const color = edgeClass === "shared_evidence" ? theme === "macaron" ? "#58a9a1" : "#3fb8b2" : edgeClass === "semantic_affinity" ? theme === "macaron" ? "#8d8eae" : "#8da1bd" : relationColors[relation.relation_type] ?? "#9f95b5";
    const contextEdge = edgeClass !== "validated";
    return {
      id: relation.relation_id,
      source: relation.source,
      target: relation.target,
      ...routeHandles(nodeById.get(relation.source), nodeById.get(relation.target)),
      type: "bezier",
      interactionWidth: 28,
      label: showLabels ? readableRelation(relation.relation_type) : undefined,
      labelStyle: { fill: contextEdge ? theme === "macaron" ? "#62667b" : "#d9e5f2" : color, fontSize: 13, fontWeight: 760 },
      labelBgStyle: { fill: labelBackground, fillOpacity: 0.94 },
      labelBgPadding: [7, 4],
      className: contextEdge ? `context-principle-edge ${edgeClass}` : "validated-principle-edge",
      style: { stroke: color, strokeWidth: relation.relation_type === "contradicts" ? 3 : contextEdge ? 1.7 : 2.2, strokeDasharray: contextEdge ? edgeClass === "shared_evidence" ? "4 6" : "2 8" : undefined, opacity: contextEdge ? 0.72 : 0.94 },
      markerEnd: contextEdge ? undefined : { type: MarkerType.ArrowClosed, color, width: 18, height: 18 },
      data: { virtual: false, relation, edgeClass },
      ariaLabel: `${readableRelation(relation.relation_type)} ${contextEdge ? "context" : "validated"} relation`,
    };
  });
  const virtual = virtualRelations.map((relation): Edge<GraphRelationData> => ({
    id: relation.relation_id,
    source: relation.source,
    target: relation.target,
    ...routeHandles(nodeById.get(relation.source), nodeById.get(relation.target)),
    type: "bezier",
    interactionWidth: 32,
    animated: true,
    label: `Potential · ${readableRelation(relation.relation_type).replace("potential ", "")}`,
    labelStyle: { fill: theme === "macaron" ? "#8b55a5" : "#dfb7ff", fontSize: 13, fontWeight: 800 },
    labelBgStyle: { fill: theme === "macaron" ? "#fff8fd" : "#19152b", fillOpacity: 0.95 },
    labelBgPadding: [6, 3],
    className: "virtual-principle-edge",
    style: { stroke: "#c77dff", strokeWidth: 2.4, strokeDasharray: "9 7" },
    markerEnd: { type: MarkerType.Arrow, color: "#9b6ad6", width: 18, height: 18 },
    data: { virtual: true, relation, edgeClass: "virtual" },
    ariaLabel: `${readableRelation(relation.relation_type)} virtual unvalidated relation`,
  }));
  return [...validated, ...virtual];
}

function layoutStorageKey(signature: string): string {
  let hash = 2166136261;
  for (let index = 0; index < signature.length; index += 1) {
    hash ^= signature.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `principia:graph-layout:v1:${(hash >>> 0).toString(16)}`;
}

export function PrincipleGraph({
  cards,
  relations,
  selectedId,
  onSelectPrinciple,
  onAnalyzePotentialRelations,
  provider,
  onGenerateVirtualPrinciples,
  onSaveVirtualPrinciple,
  onOpenSavedVirtualPrinciple,
  onOpenSavedVirtualLibrary,
}: {
  cards: PrincipleCard[];
  relations: PrincipleEdge[];
  selectedId: string;
  onSelectPrinciple: (principleId: string) => void;
  onAnalyzePotentialRelations: (principleIds: string[]) => Promise<PotentialRelationsResponse>;
  provider: ProviderChoice;
  onGenerateVirtualPrinciples: (request: { principleIds: string[]; model: string; researchDirection: string }) => Promise<VirtualGenerationResponse>;
  onSaveVirtualPrinciple: (proposal: VirtualPrincipleProposal, generation: VirtualGenerationResponse) => Promise<{ candidate_id?: string }>;
  onOpenSavedVirtualPrinciple: (candidateId: string) => void;
  onOpenSavedVirtualLibrary: () => void;
}) {
  const signature = useMemo(
    () => `${cards.map((card) => card.id).sort().join("|")}::${relations.map((edge) => edge.relation_id).sort().join("|")}`,
    [cards, relations],
  );
  const preparedNodes = useMemo(() => layoutPrinciples(cards, relations), [cards, relations]);
  const [nodes, setNodes, onNodesChange] = useNodesState<PrincipleNode>(preparedNodes);
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [selectionMode, setSelectionMode] = useState<"" | "connect" | "derive">("");
  const [connectionSelection, setConnectionSelection] = useState<string[]>([]);
  const [inspectedPrincipleId, setInspectedPrincipleId] = useState("");
  const [virtualConnectionBatches, setVirtualConnectionBatches] = useState<VirtualConnectionBatch[]>([]);
  const [virtualPrincipleBatches, setVirtualPrincipleBatches] = useState<VirtualPrincipleBatch[]>([]);
  const [artifactTrayView, setArtifactTrayView] = useState<ArtifactTrayView>("");
  const [expandedConnectionBatchId, setExpandedConnectionBatchId] = useState("");
  const [activeVirtualPrincipleBatchId, setActiveVirtualPrincipleBatchId] = useState("");
  const [focusedVirtualPrincipleId, setFocusedVirtualPrincipleId] = useState("");
  const [connectionMessage, setConnectionMessage] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [reasoningStageIndex, setReasoningStageIndex] = useState(0);
  const [selectedModel, setSelectedModel] = useState(provider.defaultModel);
  const [researchDirection, setResearchDirection] = useState("");
  const [selectionQuery, setSelectionQuery] = useState("");
  const [confirmRemote, setConfirmRemote] = useState(false);
  const [savedVirtualCandidates, setSavedVirtualCandidates] = useState<Record<string, string>>({});
  const [savingVirtualId, setSavingVirtualId] = useState("");
  const [graphTheme, setGraphTheme] = useState<GraphTheme>(() => {
    try {
      return localStorage.getItem("principia:graph-theme") === "midnight" ? "midnight" : "macaron";
    } catch {
      return "macaron";
    }
  });
  const [layoutDirty, setLayoutDirty] = useState(false);
  const [layoutSaved, setLayoutSaved] = useState(false);
  const [viewportMoving, setViewportMoving] = useState(false);
  const virtualRelations = useMemo(() => {
    const merged = new Map<string, PotentialRelation>();
    virtualConnectionBatches.forEach((batch) => batch.relations.forEach((relation) => merged.set(relation.relation_id, relation)));
    return [...merged.values()];
  }, [virtualConnectionBatches]);
  const activeVirtualPrincipleBatch = virtualPrincipleBatches.find((batch) => batch.batchId === activeVirtualPrincipleBatchId) ?? null;
  const inspectedPrinciple = cards.find((card) => card.id === inspectedPrincipleId);
  const virtualPrincipleCount = virtualPrincipleBatches.reduce((total, batch) => total + batch.items.length, 0);
  const displayedVirtualItems = activeVirtualPrincipleBatch
    ? [...activeVirtualPrincipleBatch.items].sort((left, right) => left.virtual_id === focusedVirtualPrincipleId ? -1 : right.virtual_id === focusedVirtualPrincipleId ? 1 : 0)
    : [];
  const preparedEdges = useMemo(
    () => graphEdges(relations, virtualRelations, preparedNodes, relations.length + virtualRelations.length <= 36, graphTheme),
    [relations, virtualRelations, preparedNodes, graphTheme],
  );
  const selectedCards = connectionSelection.map((id) => cards.find((card) => card.id === id)).filter((card): card is PrincipleCard => Boolean(card));
  const selectionMatches = useMemo(() => {
    const terms = selectionQuery.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    const selected = new Set(connectionSelection);
    return cards.filter((card) => {
      if (selected.has(card.id)) return false;
      const haystack = `${card.title} ${card.claim} ${card.area_labels.join(" ")}`.toLocaleLowerCase();
      return terms.every((term) => haystack.includes(term));
    }).slice(0, 8);
  }, [cards, connectionSelection, selectionQuery]);

  useEffect(() => {
    let positioned = preparedNodes;
    try {
      const stored = JSON.parse(localStorage.getItem(layoutStorageKey(signature)) ?? "{}") as Record<string, { x: number; y: number }>;
      if (stored && typeof stored === "object") {
        positioned = preparedNodes.map((node) => {
          const position = stored[node.id];
          return position && Number.isFinite(position.x) && Number.isFinite(position.y) ? { ...node, position } : node;
        });
        setLayoutSaved(Object.keys(stored).length > 0);
      }
    } catch {
      localStorage.removeItem(layoutStorageKey(signature));
      setLayoutSaved(false);
    }
    setNodes(positioned);
    setSelectedEdgeId("");
    setConnectionSelection([]);
    setInspectedPrincipleId("");
    setConnectionMessage("");
    setSelectionMode("");
    setSelectionQuery("");
    setArtifactTrayView("");
    setLayoutDirty(false);
  }, [preparedNodes, setNodes, signature]);

  useEffect(() => setSelectedModel(provider.defaultModel), [provider.defaultModel]);

  useEffect(() => {
    if (!isAnalyzing || selectionMode !== "derive") {
      setReasoningStageIndex(0);
      return undefined;
    }
    const interval = window.setInterval(() => {
      setReasoningStageIndex((current) => Math.min(reasoningStages.length - 1, current + 1));
    }, 1_700);
    return () => window.clearInterval(interval);
  }, [isAnalyzing, selectionMode]);

  useEffect(() => {
    const selectedForConnection = new Set(connectionSelection);
    setNodes((current) => current.map((node) => ({
      ...node,
      selected: node.id === selectedId,
      className: `principle-graph-node ${node.data.card.source}${node.data.isolated ? " isolated" : ""}${selectedForConnection.has(node.id) ? " virtual-selected" : ""}`,
    })));
  }, [selectedId, connectionSelection, setNodes]);

  const selectedEdge = preparedEdges.find((edge) => edge.id === selectedEdgeId);
  const selectedRelation = selectedEdge?.data?.relation;
  const selectedIsVirtual = Boolean(selectedEdge?.data?.virtual);
  const selectedEdgeClass = selectedEdge?.data?.edgeClass ?? "validated";
  const sourceCard = cards.find((card) => card.id === selectedEdge?.source);
  const targetCard = cards.find((card) => card.id === selectedEdge?.target);
  const isolatedCount = preparedNodes.filter((node) => node.data.isolated).length;

  const toggleConnectionNode = (id: string) => {
    setConnectionMessage("");
    if (!connectionSelection.includes(id)) setInspectedPrincipleId(id);
    setConnectionSelection((current) => current.includes(id)
      ? current.filter((item) => item !== id)
      : current.length < 20 ? [...current, id] : current);
    if (!connectionSelection.includes(id) && connectionSelection.length >= 20) {
      setConnectionMessage("The selection tray can hold at most twenty Principles.");
    }
  };

  const analyzeConnections = async () => {
    if (connectionSelection.length < 2) return;
    const selectedPrincipleIds = [...connectionSelection];
    setIsAnalyzing(true);
    setConnectionMessage("Comparing structured arguments…");
    try {
      const result = await onAnalyzePotentialRelations(selectedPrincipleIds);
      if (result.items.length) {
        const batchId = sessionBatchId("connection-batch");
        setVirtualConnectionBatches((current) => [...current, {
          batchId,
          createdAt: Date.now(),
          principleIds: selectedPrincipleIds,
          relations: result.items,
        }]);
        setExpandedConnectionBatchId(batchId);
        setArtifactTrayView("connections");
      }
      setConnectionSelection([]);
      setInspectedPrincipleId("");
      setSelectionMode("");
      setConnectionMessage(result.items.length
        ? `${result.items.length} temporary potential link${result.items.length === 1 ? "" : "s"} added to the Connections tray.`
        : "Those pairs already have validated relations; no virtual link was added.");
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : "Principia could not compare the selected Principles.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const deriveVirtualPrinciples = async () => {
    if (connectionSelection.length < 2 || !confirmRemote || !provider.configured) return;
    const selectedPrincipleIds = [...connectionSelection];
    setIsAnalyzing(true);
    setReasoningStageIndex(0);
    setConnectionMessage("Mapping mechanisms, testing boundaries, and synthesizing hypotheses…");
    try {
      const generation = await onGenerateVirtualPrinciples({ principleIds: selectedPrincipleIds, model: selectedModel, researchDirection });
      const batchId = sessionBatchId("principle-batch");
      setVirtualPrincipleBatches((current) => [...current, {
        batchId,
        createdAt: Date.now(),
        principleIds: selectedPrincipleIds,
        researchDirection,
        generation,
        items: generation.items,
      }]);
      setActiveVirtualPrincipleBatchId(batchId);
      setFocusedVirtualPrincipleId("");
      setConnectionSelection([]);
      setInspectedPrincipleId("");
      setSelectionMode("");
      setConfirmRemote(false);
      setConnectionMessage(`${generation.items.length} Virtual Principle${generation.items.length === 1 ? "" : "s"} ready in the Hypotheses tray.`);
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : "Virtual Principle synthesis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const saveVirtualPrinciple = async (item: GeneratedVirtualPrinciple) => {
    if (!activeVirtualPrincipleBatch) return;
    setSavingVirtualId(item.virtual_id);
    try {
      const saved = await onSaveVirtualPrinciple(item.proposal, activeVirtualPrincipleBatch.generation);
      if (!saved.candidate_id) throw new Error("The saved hypothesis did not return a local identifier.");
      setSavedVirtualCandidates((current) => ({ ...current, [item.virtual_id]: saved.candidate_id! }));
      setConnectionMessage("Saved locally. Open it from the Hypotheses tray or Saved hypotheses library.");
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : "The Virtual Principle could not be saved.");
    } finally {
      setSavingVirtualId("");
    }
  };

  const removeConnectionBatch = (batchId: string) => {
    const removedIds = new Set(virtualConnectionBatches.find((batch) => batch.batchId === batchId)?.relations.map((relation) => relation.relation_id) ?? []);
    setVirtualConnectionBatches((current) => current.filter((batch) => batch.batchId !== batchId));
    if (removedIds.has(selectedEdgeId)) setSelectedEdgeId("");
    if (expandedConnectionBatchId === batchId) setExpandedConnectionBatchId("");
    setConnectionMessage("Virtual connection batch removed. Validated relations were not changed.");
  };

  const removeVirtualConnection = (batchId: string, relationId: string) => {
    setVirtualConnectionBatches((current) => current.flatMap((batch) => {
      if (batch.batchId !== batchId) return [batch];
      const remaining = batch.relations.filter((relation) => relation.relation_id !== relationId);
      return remaining.length ? [{ ...batch, relations: remaining }] : [];
    }));
    if (selectedEdgeId === relationId) setSelectedEdgeId("");
    setConnectionMessage("Virtual connection removed. Validated relations were not changed.");
  };

  const openVirtualPrincipleBatch = (batchId: string, virtualId = "") => {
    setArtifactTrayView("");
    setSelectedEdgeId("");
    setActiveVirtualPrincipleBatchId(batchId);
    setFocusedVirtualPrincipleId(virtualId);
  };

  const removeVirtualPrinciple = (batchId: string, virtualId: string) => {
    const wasSaved = Boolean(savedVirtualCandidates[virtualId]);
    setVirtualPrincipleBatches((current) => current.flatMap((batch) => {
      if (batch.batchId !== batchId) return [batch];
      const remaining = batch.items.filter((item) => item.virtual_id !== virtualId);
      return remaining.length ? [{ ...batch, items: remaining }] : [];
    }));
    if (focusedVirtualPrincipleId === virtualId) setFocusedVirtualPrincipleId("");
    const activeBatch = virtualPrincipleBatches.find((batch) => batch.batchId === batchId);
    if (activeBatch?.items.length === 1 && activeVirtualPrincipleBatchId === batchId) setActiveVirtualPrincipleBatchId("");
    setConnectionMessage(wasSaved ? "Removed from this session tray. The locally saved hypothesis remains in Saved hypotheses." : "Unsaved Virtual Principle deleted.");
  };

  const removeVirtualPrincipleBatch = (batchId: string) => {
    const batch = virtualPrincipleBatches.find((item) => item.batchId === batchId);
    const containsSaved = batch?.items.some((item) => savedVirtualCandidates[item.virtual_id]);
    setVirtualPrincipleBatches((current) => current.filter((item) => item.batchId !== batchId));
    if (activeVirtualPrincipleBatchId === batchId) setActiveVirtualPrincipleBatchId("");
    setConnectionMessage(containsSaved ? "Batch removed from this session tray. Saved hypotheses remain in the local library." : "Virtual Principle batch deleted.");
  };

  const saveLayout = () => {
    localStorage.setItem(layoutStorageKey(signature), JSON.stringify(Object.fromEntries(nodes.map((node) => [node.id, node.position]))));
    setLayoutDirty(false);
    setLayoutSaved(true);
    setConnectionMessage("Custom graph layout saved in this browser.");
  };

  const resetLayout = () => {
    localStorage.removeItem(layoutStorageKey(signature));
    setNodes(preparedNodes);
    setLayoutDirty(false);
    setLayoutSaved(false);
    setConnectionMessage("Graph reset to the automatic scientific layout.");
  };

  const changeTheme = (theme: GraphTheme) => {
    setGraphTheme(theme);
    try { localStorage.setItem("principia:graph-theme", theme); } catch { /* Browser storage is optional. */ }
  };

  return <section className={`principle-graph-shell ${graphTheme}${viewportMoving ? " viewport-moving" : ""}`} aria-label="Interactive Principle graph">
    <ReactFlow
      nodes={nodes}
      edges={preparedEdges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeClick={(_, node) => {
        setSelectedEdgeId("");
        setInspectedPrincipleId(node.id);
        if (selectionMode) {
          toggleConnectionNode(node.id);
        }
        else onSelectPrinciple(node.id);
      }}
      onNodeDragStop={() => { setLayoutDirty(true); setLayoutSaved(false); }}
      onEdgeClick={(_, edge) => setSelectedEdgeId(edge.id)}
      nodesDraggable
      nodesConnectable={false}
      elementsSelectable
      panOnDrag
      panOnScroll
      panOnScrollMode={PanOnScrollMode.Free}
      onMoveStart={() => setViewportMoving(true)}
      onMoveEnd={() => setViewportMoving(false)}
      onlyRenderVisibleElements
      panOnScrollSpeed={0.8}
      zoomOnScroll={false}
      zoomOnPinch
      zoomOnDoubleClick
      minZoom={0.2}
      maxZoom={2.2}
      fitView={cards.length <= 10}
      fitViewOptions={{ padding: 0.18, maxZoom: 0.92 }}
      defaultViewport={{ x: 58, y: 44, zoom: 0.82 }}
      proOptions={{ hideAttribution: true }}
      colorMode={graphTheme === "macaron" ? "light" : "dark"}
    >
      <Background color={graphTheme === "macaron" ? "#c7bfd9" : "#303a61"} gap={28} size={1.2} />
      <Controls showInteractive={false} position="bottom-left" />
      {!inspectedPrinciple && !artifactTrayView ? <Panel position="top-left" className="principle-graph-legend">
        <strong>Scientific relations</strong>
        <span><i className="supports" /> supports</span>
        <span><i className="contradicts" /> contradicts</span>
        <span><i className="structural" /> other validated</span>
        <span><i className="context" /> evidence / affinity</span>
        <span><i className="virtual" /> potential</span>
      </Panel> : null}
      {!selectionMode && !selectedEdge && !activeVirtualPrincipleBatch && !artifactTrayView ? <Panel position="top-right" className="principle-graph-actions">
        <select className="graph-theme-picker" aria-label="Graph appearance" value={graphTheme} onChange={(event) => changeTheme(event.target.value as GraphTheme)}><option value="macaron">Daylight</option><option value="midnight">Midnight</option></select>
        <button onClick={() => { setSelectionMode("connect"); setConnectionMessage(""); setSelectionQuery(""); }}>Derive Virtual Connection</button>
        <button className="primary" onClick={() => { setSelectionMode("derive"); setConnectionMessage(""); setSelectionQuery(""); }}>Derive Virtual Principles</button>
        <span className="graph-action-divider" />
        <button disabled={!layoutDirty} onClick={saveLayout}>{layoutDirty ? "Save layout" : layoutSaved ? "Layout saved" : "Save layout"}</button>
        <button onClick={resetLayout}>Reset</button>
      </Panel> : null}
      {selectionMode ? <Panel position="top-right" className={`principle-connect-panel ${selectionMode}`}>
        <header className="principle-selection-header"><div><span className="eyebrow">{selectionMode === "derive" ? "LLM synthesis · unreviewed hypotheses" : "Virtual connection studio"}</span><strong>{selectionMode === "derive" ? "Derive Virtual Principles" : "Derive Virtual Connections"}</strong><small>Select 2–20 Principles</small></div><span className="selection-count"><b>{connectionSelection.length}</b>/20</span></header>
        <section className="principle-selection-tray" aria-label="Selected Principles tray"><div><strong>Selected Principles</strong>{connectionSelection.length ? <button onClick={() => { setConnectionSelection([]); setInspectedPrincipleId(""); }}>Clear all</button> : null}</div>{selectedCards.length ? <ol>{selectedCards.map((card) => <li key={card.id}><button className="principle-selection-inspect" aria-label={`View ${card.title}`} onClick={() => setInspectedPrincipleId(card.id)}><b>{card.title}</b><small>{card.source === "local" ? "Local" : card.source === "both" ? "Global + Local" : "Global"} · View details</small></button><button aria-label={`Remove ${card.title} from selection`} onClick={() => toggleConnectionNode(card.id)}>×</button></li>)}</ol> : <p>Your tray is empty. Select cards in the graph or search below.</p>}</section>
        <label className="principle-selection-search"><span>Search this graph</span><input value={selectionQuery} onChange={(event) => setSelectionQuery(event.target.value)} placeholder="Search title, claim, or area…" /></label>
        {selectionQuery.trim() ? <div className="principle-selection-results">{selectionMatches.length ? selectionMatches.map((card) => <div key={card.id}><button aria-label={`View ${card.title}`} onClick={() => setInspectedPrincipleId(card.id)}><b>{card.title}</b><small>{card.claim}</small></button><button onClick={() => { toggleConnectionNode(card.id); setSelectionQuery(""); }}><em>+ Add</em></button></div>) : <p>No unselected Principle matches this graph.</p>}</div> : null}
        {selectionMode === "derive" ? <div className="virtual-principle-config"><label><span>Reasoning model</span><select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>{provider.models.map((model) => <option key={model}>{model}</option>)}</select></label><label><span>Optional research direction</span><input value={researchDirection} onChange={(event) => setResearchDirection(event.target.value)} placeholder="e.g. seek a robust design rule" /></label><label className="virtual-egress"><input type="checkbox" checked={confirmRemote} onChange={(event) => setConfirmRemote(event.target.checked)} /><span>Send only the selected Principle records to {provider.label}. No paper PDF or full text is sent.</span></label></div> : null}
        {selectionMode === "derive" && isAnalyzing ? <section className="virtual-reasoning-progress" role="status" aria-live="polite"><header><strong>Synthesis in progress</strong><span>{Math.min(92, 18 + reasoningStageIndex * 18)}%</span></header><ol>{reasoningStages.map((stage, index) => <li key={stage.title} className={index < reasoningStageIndex ? "complete" : index === reasoningStageIndex ? "active" : "pending"}><i>{index < reasoningStageIndex ? "✓" : index + 1}</i><span><b>{stage.title}</b><small>{stage.detail}</small></span></li>)}</ol><p>These stages summarize the synthesis workflow while the selected model works; private model reasoning is not exposed.</p></section> : null}
        <div className="principle-selection-actions"><button className="primary" disabled={connectionSelection.length < 2 || isAnalyzing || (selectionMode === "derive" && (!confirmRemote || !provider.configured))} onClick={selectionMode === "derive" ? deriveVirtualPrinciples : analyzeConnections}>{isAnalyzing ? selectionMode === "derive" ? `Synthesizing · ${Math.min(92, 18 + reasoningStageIndex * 18)}%` : "Deriving connections…" : selectionMode === "derive" ? "Generate 3 Virtual Principles" : "Derive Virtual Connections"}</button>
        <button disabled={isAnalyzing} onClick={() => { setSelectionMode(""); setConnectionSelection([]); setConnectionMessage(""); }}>Cancel</button>
        </div>
        <p>{selectionMode === "derive" ? provider.configured ? "Principia maps mechanisms, stress-tests boundaries, and returns falsifiable hypotheses with separate reliability and novelty assessments." : "Configure the LLM on Home before generating Virtual Principles." : "Selected pairs are compared without changing validated relations or library measures."}</p>
      </Panel> : null}
      {inspectedPrinciple ? <Panel position="top-left" className="principle-selection-inspector">
        <header><div><span className="eyebrow">Principle details</span><strong>{selectionMode ? connectionSelection.includes(inspectedPrinciple.id) ? "In your selection" : "Available to add" : "Map record"}</strong></div><button aria-label="Close Principle details" onClick={() => setInspectedPrincipleId("")}>Close ×</button></header>
        <span className={`source-badge ${inspectedPrinciple.source}`}>{inspectedPrinciple.source === "local" ? "Local" : inspectedPrinciple.source === "both" ? "Global + Local" : "Global"}</span>
        <h3>{inspectedPrinciple.title}</h3>
        <p>{inspectedPrinciple.claim}</p>
        <dl><div><dt>Area</dt><dd>{inspectedPrinciple.area_labels.length ? inspectedPrinciple.area_labels.map((label) => label.replaceAll("-", " ")).join(" · ") : "Not categorized"}</dd></div><div><dt>Evidence</dt><dd>{inspectedPrinciple.supporting_work_count} supporting paper{inspectedPrinciple.supporting_work_count === 1 ? "" : "s"}</dd></div><div><dt>Reliability</dt><dd>{Math.round(inspectedPrinciple.reliability_score ?? 0)}</dd></div><div><dt>Influence</dt><dd>{inspectedPrinciple.influence_score == null ? "Not established" : Math.round(inspectedPrinciple.influence_score)}</dd></div></dl>
        {inspectedPrinciple.applicability ? <section><strong>Applicability</strong><p>{inspectedPrinciple.applicability}</p></section> : null}
        {selectionMode ? <button className={connectionSelection.includes(inspectedPrinciple.id) ? "" : "primary"} onClick={() => toggleConnectionNode(inspectedPrinciple.id)}>{connectionSelection.includes(inspectedPrinciple.id) ? "Remove from selection" : "+ Add to selection"}</button> : null}
      </Panel> : null}
      {isolatedCount ? <Panel position="bottom-center" className="principle-isolate-note">
        {isolatedCount} unconnected Principle{isolatedCount === 1 ? " is" : "s are"} arranged in a separate gallery to the right.
      </Panel> : null}
      <Panel position="bottom-right" className="principle-graph-hint">
        Two-finger scroll to pan · pinch to zoom · drag nodes
      </Panel>
      {virtualConnectionBatches.length || virtualPrincipleCount ? <Panel position="bottom-left" className="virtual-artifact-dock" aria-label="Virtual work tray">
        <button className={artifactTrayView === "connections" ? "active" : ""} onClick={() => setArtifactTrayView((current) => current === "connections" ? "" : "connections")}><span>⌁</span> Connections <b>{virtualRelations.length}</b></button>
        <button className={artifactTrayView === "principles" ? "active" : ""} onClick={() => setArtifactTrayView((current) => current === "principles" ? "" : "principles")}><span>✦</span> Hypotheses <b>{virtualPrincipleCount}</b></button>
      </Panel> : null}
      {artifactTrayView ? <Panel position="top-left" className="virtual-artifact-tray">
        <header><div><span className="eyebrow">Virtual work tray</span><strong>{artifactTrayView === "connections" ? "Temporary connection batches" : "Generated hypothesis batches"}</strong></div><button aria-label="Close virtual work tray" onClick={() => setArtifactTrayView("")}>Close ×</button></header>
        {artifactTrayView === "connections" ? <div className="virtual-batch-list">{virtualConnectionBatches.length ? [...virtualConnectionBatches].reverse().map((batch, reverseIndex) => <article key={batch.batchId}><header><div><strong>Connection batch {virtualConnectionBatches.length - reverseIndex}</strong><small>{batch.relations.length} potential link{batch.relations.length === 1 ? "" : "s"} · {batch.principleIds.length} Principles</small></div><div><button onClick={() => setExpandedConnectionBatchId((current) => current === batch.batchId ? "" : batch.batchId)}>{expandedConnectionBatchId === batch.batchId ? "Hide" : "View"}</button><button className="danger-subtle" onClick={() => removeConnectionBatch(batch.batchId)}>Delete</button></div></header>{expandedConnectionBatchId === batch.batchId ? <ol>{batch.relations.map((relation) => <li key={relation.relation_id}><button onClick={() => { setArtifactTrayView(""); setSelectedEdgeId(relation.relation_id); }}><b>{cards.find((card) => card.id === relation.source)?.title ?? "Source Principle"}</b><span>{readableRelation(relation.relation_type)}</span><b>{cards.find((card) => card.id === relation.target)?.title ?? "Target Principle"}</b></button><button aria-label="Delete this virtual connection" onClick={() => removeVirtualConnection(batch.batchId, relation.relation_id)}>×</button></li>)}</ol> : null}</article>) : <p>No temporary connections remain.</p>}</div> : <><button className="saved-hypothesis-path" onClick={onOpenSavedVirtualLibrary}><span>✓</span><strong>Open Saved hypotheses</strong><small>Every locally saved hypothesis remains available here after this graph session.</small></button><div className="virtual-batch-list">{virtualPrincipleBatches.length ? [...virtualPrincipleBatches].reverse().map((batch, reverseIndex) => <article key={batch.batchId}><header><div><strong>Hypothesis batch {virtualPrincipleBatches.length - reverseIndex}</strong><small>{batch.items.length} draft{batch.items.length === 1 ? "" : "s"} · {batch.principleIds.length} source Principles</small></div><div><button onClick={() => openVirtualPrincipleBatch(batch.batchId)}>Review batch</button><button className="danger-subtle" onClick={() => removeVirtualPrincipleBatch(batch.batchId)}>Delete</button></div></header><ol>{batch.items.map((item) => { const savedCandidateId = savedVirtualCandidates[item.virtual_id]; return <li key={item.virtual_id}><button onClick={() => openVirtualPrincipleBatch(batch.batchId, item.virtual_id)}><b>{item.proposal.title}</b><span>{savedCandidateId ? "Saved locally · Open" : "Unsaved draft · View"}</span></button><button aria-label={savedCandidateId ? "Remove saved hypothesis from session tray" : "Delete virtual hypothesis draft"} onClick={() => removeVirtualPrinciple(batch.batchId, item.virtual_id)}>×</button></li>; })}</ol></article>) : <p>No generated hypotheses remain in this session.</p>}</div></>}
      </Panel> : null}
      {activeVirtualPrincipleBatch ? <Panel position="top-right" className="virtual-principle-results">
        <header><div><span className="eyebrow">Virtual Principle studio</span><strong>{activeVirtualPrincipleBatch.items.length} hypotheses from deep synthesis</strong></div><button className="studio-close-button" aria-label="Close Virtual Principle studio" onClick={() => { setActiveVirtualPrincipleBatchId(""); setFocusedVirtualPrincipleId(""); }}>Close ×</button></header>
        <div className="saved-hypothesis-guide"><span>✓</span><p><strong>Saved hypotheses are never lost.</strong> Open them later from <button onClick={onOpenSavedVirtualLibrary}>Saved hypotheses</button> or reopen this batch from the floating Hypotheses tray.</p></div>
        <p>{activeVirtualPrincipleBatch.generation.disclosure}</p>
        <div>{displayedVirtualItems.map((item) => { const savedCandidateId = savedVirtualCandidates[item.virtual_id]; return <article className={item.virtual_id === focusedVirtualPrincipleId ? "focused" : ""} key={item.virtual_id}><span>{item.proposal.derivation_level.replaceAll("_", " ")}{savedCandidateId ? " · Saved locally" : " · Unsaved draft"}</span><h3>{item.proposal.title}</h3><p>{item.proposal.claim}</p><div className="virtual-score-pair"><span><b>Reliability</b><strong>{Math.round(item.proposal.reliability_score)}</strong><i><em style={{ width: `${item.proposal.reliability_score}%` }} /></i></span><span><b>Novelty</b><strong>{Math.round(item.proposal.novelty_score)}</strong><i><em style={{ width: `${item.proposal.novelty_score}%` }} /></i></span></div><details><summary>Why this hypothesis?</summary><p><b>Synthesis:</b> {item.proposal.synthesis_summary}</p><p><b>Reliability:</b> {item.proposal.reliability_rationale}</p><p><b>Novelty:</b> {item.proposal.novelty_rationale}</p><p><b>Falsifier:</b> {item.proposal.falsifier}</p></details><div className="virtual-principle-actions">{savedCandidateId ? <button className="primary" onClick={() => onOpenSavedVirtualPrinciple(savedCandidateId)}>Open saved hypothesis</button> : <button className="primary" disabled={savingVirtualId === item.virtual_id} onClick={() => saveVirtualPrinciple(item)}>{savingVirtualId === item.virtual_id ? "Saving…" : "Save as local hypothesis"}</button>}<button className="danger-subtle" onClick={() => removeVirtualPrinciple(activeVirtualPrincipleBatch.batchId, item.virtual_id)}>{savedCandidateId ? "Remove from tray" : "Delete draft"}</button></div></article>; })}</div>
      </Panel> : null}
      {selectedRelation ? <Panel position="top-right" className={`principle-edge-inspector${selectedIsVirtual ? " virtual" : selectedEdgeClass !== "validated" ? " context" : ""}`}>
        <button className="edge-close" aria-label="Close relation details" onClick={() => setSelectedEdgeId("")}>×</button>
        <span className="eyebrow">{selectedIsVirtual ? "Potential relationship · not validated" : selectedEdgeClass === "shared_evidence" ? "Shared-paper context · not scientific support" : selectedEdgeClass === "semantic_affinity" ? "Semantic affinity · not validated" : "Validated scientific relation"}</span>
        <h3>{readableRelation(selectedRelation.relation_type)}</h3>
        <button onClick={() => onSelectPrinciple(selectedRelation.source)}>{sourceCard?.title ?? "Source Principle"}</button>
        <span className="edge-direction">↓ {readableRelation(selectedRelation.relation_type)} ↓</span>
        <button onClick={() => onSelectPrinciple(selectedRelation.target)}>{targetCard?.title ?? "Target Principle"}</button>
        <p>{selectedRelation.rationale || "This relation passed the library's recorded relation checks."}</p>
        {selectedIsVirtual ? <><p><strong>Shared concepts:</strong> {(selectedRelation as PotentialRelation).shared_concepts.join(", ") || "No strong lexical overlap"}</p><small>Temporary only. This link is not saved and cannot affect Reliability or Influence.</small></> : null}
      </Panel> : null}
    </ReactFlow>
    <div className="principle-graph-status" role="status" aria-live="polite">{connectionMessage}</div>
    <div className="sr-only" aria-live="polite">{selectedRelation ? `${sourceCard?.title} ${readableRelation(selectedRelation.relation_type)} ${targetCard?.title}` : ""}</div>
  </section>;
}
