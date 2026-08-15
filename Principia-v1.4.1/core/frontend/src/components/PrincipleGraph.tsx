import { useEffect, useMemo, useRef, useState } from "react";
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

type ProviderChoice = { provider: string; label: string; configured: boolean; defaultModel: string; models: string[] };

const WIDTH = 348;
const HEIGHT = 226;

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

function PrincipleNodeCard({ data }: NodeProps<PrincipleNode>) {
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
      <div className="principle-graph-node-metrics"><span><i style={{ width: `${reliability}%` }} /><b>Reliability</b><em>{Math.round(reliability)}</em></span><span><i style={{ width: `${influence}%` }} /><b>Influence</b><em>{Math.round(influence)}</em></span></div>
    </div>
  </>;
}

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
}) {
  const shellRef = useRef<HTMLElement | null>(null);
  const signature = useMemo(
    () => `${cards.map((card) => card.id).sort().join("|")}::${relations.map((edge) => edge.relation_id).sort().join("|")}`,
    [cards, relations],
  );
  const preparedNodes = useMemo(() => layoutPrinciples(cards, relations), [signature]);
  const [nodes, setNodes, onNodesChange] = useNodesState<PrincipleNode>(preparedNodes);
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [selectionMode, setSelectionMode] = useState<"" | "connect" | "derive">("");
  const [connectionSelection, setConnectionSelection] = useState<string[]>([]);
  const [virtualRelations, setVirtualRelations] = useState<PotentialRelation[]>([]);
  const [connectionMessage, setConnectionMessage] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [selectedModel, setSelectedModel] = useState(provider.defaultModel);
  const [researchDirection, setResearchDirection] = useState("");
  const [selectionQuery, setSelectionQuery] = useState("");
  const [confirmRemote, setConfirmRemote] = useState(false);
  const [virtualGeneration, setVirtualGeneration] = useState<VirtualGenerationResponse | null>(null);
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
  const preparedEdges = useMemo(
    () => graphEdges(relations, virtualRelations, nodes, relations.length + virtualRelations.length <= 36, graphTheme),
    [relations, virtualRelations, nodes, graphTheme],
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
    setVirtualRelations([]);
    setConnectionMessage("");
    setSelectionMode("");
    setSelectionQuery("");
    setVirtualGeneration(null);
    setLayoutDirty(false);
  }, [preparedNodes, setNodes, signature]);

  useEffect(() => setSelectedModel(provider.defaultModel), [provider.defaultModel]);

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
    setConnectionSelection((current) => current.includes(id)
      ? current.filter((item) => item !== id)
      : current.length < 20 ? [...current, id] : current);
    if (!connectionSelection.includes(id) && connectionSelection.length >= 20) {
      setConnectionMessage("The selection tray can hold at most twenty Principles.");
    }
  };

  const analyzeConnections = async () => {
    if (connectionSelection.length < 2) return;
    setIsAnalyzing(true);
    setConnectionMessage("Comparing structured arguments…");
    try {
      const result = await onAnalyzePotentialRelations(connectionSelection);
      setVirtualRelations((current) => {
        const merged = new Map(current.map((relation) => [relation.relation_id, relation]));
        result.items.forEach((relation) => merged.set(relation.relation_id, relation));
        return [...merged.values()];
      });
      setConnectionSelection([]);
      setSelectionMode("");
      setConnectionMessage(result.items.length
        ? `${result.items.length} temporary potential link${result.items.length === 1 ? "" : "s"} added. Click a dashed link to inspect it.`
        : "Those pairs already have validated relations; no virtual link was added.");
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : "Principia could not compare the selected Principles.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const deriveVirtualPrinciples = async () => {
    if (connectionSelection.length < 2 || !confirmRemote || !provider.configured) return;
    setIsAnalyzing(true);
    setConnectionMessage("Mapping mechanisms, testing boundaries, and synthesizing hypotheses…");
    try {
      const generation = await onGenerateVirtualPrinciples({ principleIds: connectionSelection, model: selectedModel, researchDirection });
      setVirtualGeneration(generation);
      setConnectionSelection([]);
      setSelectionMode("");
      setConfirmRemote(false);
      setConnectionMessage(`${generation.items.length} Virtual Principle${generation.items.length === 1 ? "" : "s"} ready for review.`);
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : "Virtual Principle synthesis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const saveVirtualPrinciple = async (item: GeneratedVirtualPrinciple) => {
    if (!virtualGeneration) return;
    setSavingVirtualId(item.virtual_id);
    try {
      const saved = await onSaveVirtualPrinciple(item.proposal, virtualGeneration);
      if (!saved.candidate_id) throw new Error("The saved hypothesis did not return a local identifier.");
      setSavedVirtualCandidates((current) => ({ ...current, [item.virtual_id]: saved.candidate_id! }));
      setConnectionMessage("Saved under Local Results → Saved Virtual Principles.");
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : "The Virtual Principle could not be saved.");
    } finally {
      setSavingVirtualId("");
    }
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

  return <section ref={shellRef} className={`principle-graph-shell ${graphTheme}`} aria-label="Interactive Principle graph">
    <ReactFlow
      key={signature}
      nodes={nodes}
      edges={preparedEdges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeClick={(_, node) => {
        setSelectedEdgeId("");
        if (selectionMode) toggleConnectionNode(node.id);
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
      <Panel position="top-left" className="principle-graph-legend">
        <strong>Scientific relations</strong>
        <span><i className="supports" /> supports</span>
        <span><i className="contradicts" /> contradicts</span>
        <span><i className="structural" /> other validated</span>
        <span><i className="context" /> evidence / affinity</span>
        <span><i className="virtual" /> potential</span>
      </Panel>
      {!selectionMode && !selectedEdge && !virtualGeneration ? <Panel position="top-right" className="principle-graph-actions">
        <label className="graph-theme-picker"><span>Palette</span><select aria-label="Graph palette" value={graphTheme} onChange={(event) => changeTheme(event.target.value as GraphTheme)}><option value="macaron">Macaron</option><option value="midnight">Midnight</option></select></label>
        <button onClick={() => { setSelectionMode("connect"); setConnectionMessage(""); setSelectionQuery(""); }}>Derive Virtual Connection</button>
        <button className="primary" onClick={() => { setSelectionMode("derive"); setConnectionMessage(""); setSelectionQuery(""); }}>Derive Virtual Principles</button>
        <span className="graph-action-divider" />
        <button disabled={!layoutDirty} onClick={saveLayout}>{layoutDirty ? "Save layout" : layoutSaved ? "Layout saved" : "Save layout"}</button>
        <button onClick={resetLayout}>Reset</button>
        <button onClick={() => shellRef.current?.requestFullscreen?.()}>Present</button>
        {virtualRelations.length ? <button onClick={() => { setVirtualRelations([]); setSelectedEdgeId(""); setConnectionMessage("Temporary links cleared."); }}>Clear virtual links</button> : null}
      </Panel> : null}
      {selectionMode ? <Panel position="top-right" className={`principle-connect-panel ${selectionMode}`}>
        <header className="principle-selection-header"><div><span className="eyebrow">{selectionMode === "derive" ? "LLM synthesis · unreviewed hypotheses" : "Virtual connection studio"}</span><strong>{selectionMode === "derive" ? "Derive Virtual Principles" : "Derive Virtual Connections"}</strong><small>Select 2–20 Principles</small></div><span className="selection-count"><b>{connectionSelection.length}</b>/20</span></header>
        <section className="principle-selection-tray" aria-label="Selected Principles tray"><div><strong>Selected Principles</strong>{connectionSelection.length ? <button onClick={() => setConnectionSelection([])}>Clear all</button> : null}</div>{selectedCards.length ? <ol>{selectedCards.map((card) => <li key={card.id}><span><b>{card.title}</b><small>{card.source === "local" ? "Local" : card.source === "both" ? "Global + Local" : "Global"}</small></span><button aria-label={`Remove ${card.title} from selection`} onClick={() => toggleConnectionNode(card.id)}>×</button></li>)}</ol> : <p>Your tray is empty. Select cards in the graph or search below.</p>}</section>
        <label className="principle-selection-search"><span>Search this graph</span><input value={selectionQuery} onChange={(event) => setSelectionQuery(event.target.value)} placeholder="Search title, claim, or area…" /></label>
        {selectionQuery.trim() ? <div className="principle-selection-results">{selectionMatches.length ? selectionMatches.map((card) => <button key={card.id} onClick={() => { toggleConnectionNode(card.id); setSelectionQuery(""); }}><span><b>{card.title}</b><small>{card.claim}</small></span><em>+ Add</em></button>) : <p>No unselected Principle matches this graph.</p>}</div> : null}
        {selectionMode === "derive" ? <div className="virtual-principle-config"><label><span>Reasoning model</span><select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>{provider.models.map((model) => <option key={model}>{model}</option>)}</select></label><label><span>Optional research direction</span><input value={researchDirection} onChange={(event) => setResearchDirection(event.target.value)} placeholder="e.g. seek a robust design rule" /></label><label className="virtual-egress"><input type="checkbox" checked={confirmRemote} onChange={(event) => setConfirmRemote(event.target.checked)} /><span>Send only the selected Principle records to {provider.label}. No paper PDF or full text is sent.</span></label></div> : null}
        <div className="principle-selection-actions"><button className="primary" disabled={connectionSelection.length < 2 || isAnalyzing || (selectionMode === "derive" && (!confirmRemote || !provider.configured))} onClick={selectionMode === "derive" ? deriveVirtualPrinciples : analyzeConnections}>{isAnalyzing ? selectionMode === "derive" ? "Deep reasoning…" : "Deriving connections…" : selectionMode === "derive" ? "Generate 3 Virtual Principles" : "Derive Virtual Connections"}</button>
        <button disabled={isAnalyzing} onClick={() => { setSelectionMode(""); setConnectionSelection([]); setConnectionMessage(""); }}>Cancel</button>
        </div>
        <p>{selectionMode === "derive" ? provider.configured ? "Principia maps mechanisms, stress-tests boundaries, and returns falsifiable hypotheses with separate reliability and novelty assessments." : "Configure the LLM on Home before generating Virtual Principles." : "Selected pairs are compared without changing validated relations or library measures."}</p>
      </Panel> : null}
      {isolatedCount ? <Panel position="bottom-center" className="principle-isolate-note">
        {isolatedCount} unconnected Principle{isolatedCount === 1 ? " is" : "s are"} arranged in a separate gallery to the right.
      </Panel> : null}
      <Panel position="bottom-right" className="principle-graph-hint">
        Two-finger scroll to pan · pinch to zoom · drag nodes
      </Panel>
      {virtualGeneration ? <Panel position="top-right" className="virtual-principle-results">
        <header><div><span className="eyebrow">Virtual Principle studio</span><strong>{virtualGeneration.items.length} hypotheses from deep synthesis</strong></div><button aria-label="Close Virtual Principle results" onClick={() => setVirtualGeneration(null)}>×</button></header>
        <p>{virtualGeneration.disclosure}</p>
        <div>{virtualGeneration.items.map((item) => { const savedCandidateId = savedVirtualCandidates[item.virtual_id]; return <article key={item.virtual_id}><span>{item.proposal.derivation_level.replaceAll("_", " ")}</span><h3>{item.proposal.title}</h3><p>{item.proposal.claim}</p><div className="virtual-score-pair"><span><b>Reliability</b><strong>{Math.round(item.proposal.reliability_score)}</strong><i><em style={{ width: `${item.proposal.reliability_score}%` }} /></i></span><span><b>Novelty</b><strong>{Math.round(item.proposal.novelty_score)}</strong><i><em style={{ width: `${item.proposal.novelty_score}%` }} /></i></span></div><details><summary>Why this hypothesis?</summary><p><b>Synthesis:</b> {item.proposal.synthesis_summary}</p><p><b>Reliability:</b> {item.proposal.reliability_rationale}</p><p><b>Novelty:</b> {item.proposal.novelty_rationale}</p><p><b>Falsifier:</b> {item.proposal.falsifier}</p></details>{savedCandidateId ? <button className="primary" onClick={() => onOpenSavedVirtualPrinciple(savedCandidateId)}>Open saved hypothesis</button> : <button className="primary" disabled={savingVirtualId === item.virtual_id} onClick={() => saveVirtualPrinciple(item)}>{savingVirtualId === item.virtual_id ? "Saving…" : "Save as local hypothesis"}</button>}</article>; })}</div>
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
