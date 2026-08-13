import { useEffect, useMemo, useState } from "react";
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
type PrincipleNodeData = { card: PrincipleCard; isolated: boolean };
type PrincipleNode = Node<PrincipleNodeData, "principle">;
type GraphRelationData = {
  virtual: boolean;
  relation: PrincipleEdge | PotentialRelation;
};

const WIDTH = 226;
const HEIGHT = 122;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

const relationColors: Record<string, string> = {
  supports: "#258164",
  contradicts: "#c65462",
  refines: "#3978b8",
  generalizes: "#6b55d9",
  specializes: "#92703a",
  depends_on: "#537589",
  analogous_to: "#8b5aad",
};

function readableRelation(value: string): string {
  return value.replace(/^potential_/, "potential ").replaceAll("_", " ");
}

function PrincipleNodeCard({ data }: NodeProps<PrincipleNode>) {
  const { card } = data;
  return <>
    {[Position.Top, Position.Right, Position.Bottom, Position.Left].flatMap((position) => [
      <Handle key={`source-${position}`} id={`source-${position}`} type="source" position={position} isConnectable={false} />,
      <Handle key={`target-${position}`} id={`target-${position}`} type="target" position={position} isConnectable={false} />,
    ])}
    <div className="principle-graph-node-content">
      <div><span>{card.source === "local" ? "Local" : "Global"}</span><span>{card.supporting_work_count} paper{card.supporting_work_count === 1 ? "" : "s"}</span></div>
      <strong>{card.title}</strong>
      <small>{card.area_labels.length ? card.area_labels.slice(0, 2).map((area) => area.replaceAll("-", " ")).join(" · ") : "Not categorized"}</small>
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
  const componentCenters = new Map<string, { x: number; y: number }>();
  const componentColumns = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(components.length))));

  components.forEach((component, componentIndex) => {
    const column = componentIndex % componentColumns;
    const row = Math.floor(componentIndex / componentColumns);
    const center = { x: 480 + column * 940, y: 410 + row * 760 };
    component.forEach((id, index) => {
      const radius = index === 0 ? 0 : 170 + 115 * Math.sqrt(index - 1);
      const angle = index * GOLDEN_ANGLE + componentIndex * 0.37;
      positions.set(id, {
        x: center.x + Math.cos(angle) * radius,
        y: center.y + Math.sin(angle) * radius * 0.78,
      });
      componentCenters.set(id, center);
    });
  });

  const connectedIds = components.flat();
  const linked = relations.filter((relation) => positions.has(relation.source) && positions.has(relation.target));
  for (let iteration = 0; iteration < 100; iteration += 1) {
    const movement = new Map(connectedIds.map((id) => [id, { x: 0, y: 0 }]));
    for (let leftIndex = 0; leftIndex < connectedIds.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < connectedIds.length; rightIndex += 1) {
        const leftId = connectedIds[leftIndex];
        const rightId = connectedIds[rightIndex];
        const left = positions.get(leftId)!;
        const right = positions.get(rightId)!;
        let dx = right.x - left.x;
        let dy = right.y - left.y;
        if (Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01) {
          dx = Math.cos(rightIndex * GOLDEN_ANGLE);
          dy = Math.sin(rightIndex * GOLDEN_ANGLE);
        }
        const distance = Math.max(24, Math.hypot(dx, dy));
        const repulsion = Math.min(17, 33000 / (distance * distance));
        movement.get(leftId)!.x -= (dx / distance) * repulsion;
        movement.get(leftId)!.y -= (dy / distance) * repulsion;
        movement.get(rightId)!.x += (dx / distance) * repulsion;
        movement.get(rightId)!.y += (dy / distance) * repulsion;
        const overlapX = WIDTH + 34 - Math.abs(dx);
        const overlapY = HEIGHT + 30 - Math.abs(dy);
        if (overlapX > 0 && overlapY > 0) {
          if (overlapX / WIDTH < overlapY / HEIGHT) {
            const correction = Math.min(20, overlapX * 0.14) * (dx >= 0 ? 1 : -1);
            movement.get(leftId)!.x -= correction;
            movement.get(rightId)!.x += correction;
          } else {
            const correction = Math.min(20, overlapY * 0.16) * (dy >= 0 ? 1 : -1);
            movement.get(leftId)!.y -= correction;
            movement.get(rightId)!.y += correction;
          }
        }
      }
    }
    linked.forEach((relation) => {
      const source = positions.get(relation.source)!;
      const target = positions.get(relation.target)!;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const attraction = (distance - 300) * 0.01;
      movement.get(relation.source)!.x += (dx / distance) * attraction;
      movement.get(relation.source)!.y += (dy / distance) * attraction;
      movement.get(relation.target)!.x -= (dx / distance) * attraction;
      movement.get(relation.target)!.y -= (dy / distance) * attraction;
    });
    connectedIds.forEach((id) => {
      const position = positions.get(id)!;
      const center = componentCenters.get(id)!;
      const delta = movement.get(id)!;
      delta.x += (center.x - position.x) * 0.0013;
      delta.y += (center.y - position.y) * 0.0013;
      position.x += Math.max(-17, Math.min(17, delta.x));
      position.y += Math.max(-17, Math.min(17, delta.y));
    });
  }

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
): Edge<GraphRelationData>[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const validated = relations.map((relation): Edge<GraphRelationData> => {
    const color = relationColors[relation.relation_type] ?? "#6d6879";
    return {
      id: relation.relation_id,
      source: relation.source,
      target: relation.target,
      ...routeHandles(nodeById.get(relation.source), nodeById.get(relation.target)),
      type: "bezier",
      interactionWidth: 28,
      label: showLabels ? readableRelation(relation.relation_type) : undefined,
      labelStyle: { fill: color, fontSize: 8, fontWeight: 700 },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.9 },
      labelBgPadding: [5, 3],
      style: { stroke: color, strokeWidth: relation.relation_type === "contradicts" ? 2.5 : 1.8 },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      data: { virtual: false, relation },
      ariaLabel: `${readableRelation(relation.relation_type)} validated relation`,
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
    labelStyle: { fill: "#7650b8", fontSize: 8, fontWeight: 800 },
    labelBgStyle: { fill: "#faf7ff", fillOpacity: 0.95 },
    labelBgPadding: [6, 3],
    className: "virtual-principle-edge",
    style: { stroke: "#9b6ad6", strokeWidth: 2, strokeDasharray: "8 7" },
    markerEnd: { type: MarkerType.Arrow, color: "#9b6ad6", width: 18, height: 18 },
    data: { virtual: true, relation },
    ariaLabel: `${readableRelation(relation.relation_type)} virtual unvalidated relation`,
  }));
  return [...validated, ...virtual];
}

export function PrincipleGraph({
  cards,
  relations,
  selectedId,
  onSelectPrinciple,
  onAnalyzePotentialRelations,
}: {
  cards: PrincipleCard[];
  relations: PrincipleEdge[];
  selectedId: string;
  onSelectPrinciple: (principleId: string) => void;
  onAnalyzePotentialRelations: (principleIds: string[]) => Promise<PotentialRelationsResponse>;
}) {
  const signature = useMemo(
    () => `${cards.map((card) => card.id).sort().join("|")}::${relations.map((edge) => edge.relation_id).sort().join("|")}`,
    [cards, relations],
  );
  const preparedNodes = useMemo(() => layoutPrinciples(cards, relations), [signature]);
  const [nodes, setNodes, onNodesChange] = useNodesState<PrincipleNode>(preparedNodes);
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [connectMode, setConnectMode] = useState(false);
  const [connectionSelection, setConnectionSelection] = useState<string[]>([]);
  const [virtualRelations, setVirtualRelations] = useState<PotentialRelation[]>([]);
  const [connectionMessage, setConnectionMessage] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const preparedEdges = useMemo(
    () => graphEdges(relations, virtualRelations, nodes, relations.length + virtualRelations.length <= 36),
    [relations, virtualRelations, nodes],
  );

  useEffect(() => {
    setNodes(preparedNodes);
    setSelectedEdgeId("");
    setConnectionSelection([]);
    setVirtualRelations([]);
    setConnectionMessage("");
    setConnectMode(false);
  }, [preparedNodes, setNodes]);

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
  const sourceCard = cards.find((card) => card.id === selectedEdge?.source);
  const targetCard = cards.find((card) => card.id === selectedEdge?.target);
  const isolatedCount = preparedNodes.filter((node) => node.data.isolated).length;

  const toggleConnectionNode = (id: string) => {
    setConnectionMessage("");
    setConnectionSelection((current) => current.includes(id)
      ? current.filter((item) => item !== id)
      : current.length < 6 ? [...current, id] : current);
    if (!connectionSelection.includes(id) && connectionSelection.length >= 6) {
      setConnectionMessage("Select at most six Principles at a time.");
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
      setConnectMode(false);
      setConnectionMessage(result.items.length
        ? `${result.items.length} temporary potential link${result.items.length === 1 ? "" : "s"} added. Click a dashed link to inspect it.`
        : "Those pairs already have validated relations; no virtual link was added.");
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : "Principia could not compare the selected Principles.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  return <section className="principle-graph-shell" aria-label="Interactive Principle graph">
    <ReactFlow
      key={signature}
      nodes={nodes}
      edges={preparedEdges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeClick={(_, node) => {
        setSelectedEdgeId("");
        if (connectMode) toggleConnectionNode(node.id);
        else onSelectPrinciple(node.id);
      }}
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
      minZoom={0.18}
      maxZoom={2.2}
      fitView={cards.length <= 12}
      fitViewOptions={{ padding: 0.18, maxZoom: 1 }}
      defaultViewport={{ x: 50, y: 35, zoom: 0.62 }}
      proOptions={{ hideAttribution: true }}
      colorMode="light"
    >
      <Background color="#d9d4e9" gap={22} size={1} />
      <Controls showInteractive={false} position="bottom-left" />
      <Panel position="top-left" className="principle-graph-legend">
        <strong>Scientific relations</strong>
        <span><i className="supports" /> supports</span>
        <span><i className="contradicts" /> contradicts</span>
        <span><i className="structural" /> refines or relates</span>
        <span><i className="virtual" /> potential</span>
      </Panel>
      {!connectMode && !selectedEdge ? <Panel position="top-right" className="principle-graph-actions">
        <button className="primary" onClick={() => { setConnectMode(true); setConnectionMessage(""); }}>Compare &amp; connect</button>
        {virtualRelations.length ? <button onClick={() => { setVirtualRelations([]); setSelectedEdgeId(""); setConnectionMessage("Temporary links cleared."); }}>Clear virtual links</button> : null}
      </Panel> : null}
      {connectMode ? <Panel position="top-center" className="principle-connect-panel">
        <div><span className="eyebrow">Temporary relationship analysis</span><strong>Select 2–6 Principles</strong><small>{connectionSelection.length} selected</small></div>
        <button className="primary" disabled={connectionSelection.length < 2 || isAnalyzing} onClick={analyzeConnections}>{isAnalyzing ? "Comparing…" : "Analyze potential links"}</button>
        <button disabled={isAnalyzing} onClick={() => { setConnectMode(false); setConnectionSelection([]); setConnectionMessage(""); }}>Cancel</button>
        <p>Selected pairs are compared without changing validated relations or library measures.</p>
      </Panel> : null}
      {isolatedCount ? <Panel position="bottom-center" className="principle-isolate-note">
        {isolatedCount} unconnected Principle{isolatedCount === 1 ? " is" : "s are"} arranged in a separate gallery to the right.
      </Panel> : null}
      <Panel position="bottom-right" className="principle-graph-hint">
        Two-finger scroll to pan · pinch to zoom · drag nodes
      </Panel>
      {selectedRelation ? <Panel position="top-right" className={`principle-edge-inspector${selectedIsVirtual ? " virtual" : ""}`}>
        <button className="edge-close" aria-label="Close relation details" onClick={() => setSelectedEdgeId("")}>×</button>
        <span className="eyebrow">{selectedIsVirtual ? "Potential relationship · not validated" : "Validated scientific relation"}</span>
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
