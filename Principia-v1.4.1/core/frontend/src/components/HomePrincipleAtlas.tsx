import { memo, useMemo, useRef, useState } from "react";
import { Background, Controls, Handle, Panel, PanOnScrollMode, Position, ReactFlow, type Edge, type Node, type NodeProps, type Viewport } from "@xyflow/react";
import type { components } from "../api/schema";

type PrincipleCard = components["schemas"]["PrincipleCardResponse"];
type PrincipleEdge = components["schemas"]["PrincipleGraphEdgeResponse"];
export type AtlasArea = { value: string; count: number };
type AtlasNodeData = { kind: "principle"; card: PrincipleCard } | { kind: "area"; area: string; count: number };
type AtlasNode = Node<AtlasNodeData, "atlas">;
type Density = "full" | "title" | "dot" | "area";

const CARD_WIDTH = 300;
const CARD_HEIGHT = 174;
const AREA_WIDTH = 410;
const AREA_HEIGHT = 190;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const edgeColors: Record<string, string> = { supports: "#4b9f80", contradicts: "#d66479", refines: "#638fc4", generalizes: "#826bc4", specializes: "#b98642", depends_on: "#58979f", analogous_to: "#9d69ae" };
const areaLabel = (value: string) => value.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const cardArea = (card: PrincipleCard) => card.area_labels[0] || "General";
const areaNodeId = (area: string) => `area:${area}`;

const AtlasNodeView = memo(function AtlasNodeView({ data }: NodeProps<AtlasNode>) {
  if (data.kind === "area") return <div className="home-atlas-area-node-content"><span aria-hidden="true" /><small>Scientific area</small><strong>{areaLabel(data.area)}</strong><em>{data.count.toLocaleString()} Principle{data.count === 1 ? "" : "s"}</em></div>;
  const card = data.card;
  return <div className="home-atlas-node-content"><Handle type="target" position={Position.Left} /><span className="home-atlas-node-dot" aria-hidden="true" /><div className="home-atlas-node-copy"><small>{areaLabel(cardArea(card))} · {card.supporting_work_count} paper{card.supporting_work_count === 1 ? "" : "s"}</small><strong>{card.title}</strong><p>{card.claim}</p></div><Handle type="source" position={Position.Right} /></div>;
});
const nodeTypes = { atlas: AtlasNodeView };

function densityForZoom(zoom: number): Density {
  if (zoom >= 0.68) return "full";
  if (zoom >= 0.38) return "title";
  if (zoom >= 0.21) return "dot";
  return "area";
}
function areaCenter(index: number, total: number) {
  if (total <= 1) return { x: 0, y: 0 };
  const radius = Math.max(1_050, total * 95);
  const angle = -Math.PI / 2 + (index / total) * Math.PI * 2;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

export function HomePrincipleAtlas({ cards, relations, areas, selectedAreas, totalCount, query, loading, loadingMore, hasMore, onLoadMore, onToggleArea, onClearAreas }: {
  cards: PrincipleCard[]; relations: PrincipleEdge[]; areas: AtlasArea[]; selectedAreas: string[]; totalCount: number; query: string; loading: boolean; loadingMore: boolean; hasMore: boolean; onLoadMore: () => void; onToggleArea: (area: string) => void; onClearAreas: () => void;
}) {
  const [density, setDensity] = useState<Density>("title");
  const densityRef = useRef<Density>("title");
  const [selectedId, setSelectedId] = useState("");
  const visitedRegions = useRef(new Set<string>());
  const lastLoadAt = useRef(0);
  const visibleAreas = useMemo(() => {
    const source = selectedAreas.length ? areas.filter((item) => selectedAreas.includes(item.value)) : areas;
    return source.length ? source : Array.from(new Set(cards.map(cardArea))).map((value) => ({ value, count: cards.filter((card) => cardArea(card) === value).length }));
  }, [areas, cards, selectedAreas]);
  const centers = useMemo(() => new Map(visibleAreas.map((item, index) => [item.value, areaCenter(index, visibleAreas.length)])), [visibleAreas]);
  const cardsByArea = useMemo(() => { const output = new Map<string, PrincipleCard[]>(); cards.forEach((card) => output.set(cardArea(card), [...(output.get(cardArea(card)) ?? []), card])); return output; }, [cards]);
  const principleNodes = useMemo<AtlasNode[]>(() => cards.map((card) => {
    const group = cardsByArea.get(cardArea(card)) ?? [card];
    const index = group.findIndex((item) => item.id === card.id);
    const center = centers.get(cardArea(card)) ?? { x: 0, y: 0 };
    const radius = index ? 220 * Math.sqrt(index) : 0;
    const angle = index * GOLDEN_ANGLE;
    return { id: card.id, type: "atlas", position: { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius }, data: { kind: "principle", card }, className: `home-atlas-node ${card.source}`, style: { width: CARD_WIDTH, height: CARD_HEIGHT } };
  }), [cards, cardsByArea, centers]);
  const areaNodes = useMemo<AtlasNode[]>(() => visibleAreas.map((item) => { const center = centers.get(item.value) ?? { x: 0, y: 0 }; return { id: areaNodeId(item.value), type: "atlas", position: { x: center.x - AREA_WIDTH / 2, y: center.y - AREA_HEIGHT / 2 }, data: { kind: "area", area: item.value, count: item.count }, className: "home-atlas-area-node", style: { width: AREA_WIDTH, height: AREA_HEIGHT } }; }), [centers, visibleAreas]);
  const nodeIds = useMemo(() => new Set(cards.map((card) => card.id)), [cards]);
  const principleEdges = useMemo<Edge[]>(() => {
    const output: Edge[] = relations.filter((relation) => nodeIds.has(relation.source) && nodeIds.has(relation.target)).map((relation) => ({ id: relation.relation_id, source: relation.source, target: relation.target, type: "bezier", className: `home-atlas-edge ${relation.edge_class}`, style: { stroke: relation.edge_class === "validated" ? (edgeColors[relation.relation_type] ?? "#8068af") : "#9985a8", strokeWidth: relation.edge_class === "validated" ? 2.7 : 1.8, strokeDasharray: relation.edge_class === "validated" ? undefined : "5 6", opacity: relation.edge_class === "validated" ? 0.9 : 0.62 } }));
    const connected = new Set(output.map((edge) => [edge.source, edge.target].sort().join("\0")));
    cardsByArea.forEach((group, area) => { for (let index = 1; index < group.length; index += 1) { const source = group[index - 1].id; const target = group[index].id; const key = [source, target].sort().join("\0"); if (connected.has(key)) continue; connected.add(key); output.push({ id: `area-context:${area}:${index}`, source, target, type: "bezier", className: "home-atlas-edge area-context", style: { stroke: "#aa8db0", strokeWidth: 1.45, strokeDasharray: "3 7", opacity: 0.48 } }); } });
    return output;
  }, [cardsByArea, nodeIds, relations]);
  const areaEdges = useMemo<Edge[]>(() => {
    const byCard = new Map(cards.map((card) => [card.id, cardArea(card)]));
    const weights = new Map<string, number>();
    relations.forEach((relation) => { const sourceArea = byCard.get(relation.source); const targetArea = byCard.get(relation.target); if (!sourceArea || !targetArea || sourceArea === targetArea) return; const key = [sourceArea, targetArea].sort().join("\0"); weights.set(key, (weights.get(key) ?? 0) + 1); });
    const output = Array.from(weights, ([key, weight]) => { const [source, target] = key.split("\0"); return { id: `area-edge:${key}`, source: areaNodeId(source), target: areaNodeId(target), type: "bezier", className: "home-atlas-area-edge", style: { stroke: "#8d73a8", strokeWidth: Math.min(8, 3 + weight), opacity: 0.68 } } as Edge; });
    if (!output.length && visibleAreas.length > 1) visibleAreas.forEach((item, index) => output.push({ id: `area-ring:${index}`, source: areaNodeId(item.value), target: areaNodeId(visibleAreas[(index + 1) % visibleAreas.length].value), type: "bezier", className: "home-atlas-area-edge contextual", style: { stroke: "#aa94b8", strokeWidth: 3, strokeDasharray: "12 14", opacity: 0.45 } }));
    return output;
  }, [cards, relations, visibleAreas]);
  const selectedCard = cards.find((card) => card.id === selectedId);
  const handleMove = (_event: MouseEvent | TouchEvent | null, viewport: Viewport) => { const next = densityForZoom(viewport.zoom); if (densityRef.current === next) return; densityRef.current = next; setDensity(next); };
  const handleMoveEnd = (event: MouseEvent | TouchEvent | null, viewport: Viewport) => { handleMove(event, viewport); if (!event || !hasMore || loadingMore || densityRef.current === "area") return; const region = `${Math.round(viewport.x / 620)}:${Math.round(viewport.y / 500)}:${Math.round(viewport.zoom * 4)}`; if (visitedRegions.current.has(region)) return; const now = Date.now(); if (now - lastLoadAt.current < 500) return; visitedRegions.current.add(region); lastLoadAt.current = now; onLoadMore(); };

  return <section className={`home-atlas-shell density-${density}`} aria-label={query ? `Principles related to ${query}` : "Global Principles map"}>
    {loading && !cards.length ? <div className="home-atlas-loading" role="status"><span /><strong>Opening the Global Principles map…</strong><small>Loading only the first visible region</small></div> : null}
    {!loading && !cards.length ? <div className="home-atlas-empty"><strong>No matching Principles yet</strong><span>Try describing the problem in a different way or clear the search.</span></div> : null}
    {cards.length ? <ReactFlow nodes={density === "area" ? areaNodes : principleNodes} edges={density === "area" ? areaEdges : principleEdges} nodeTypes={nodeTypes} onNodeClick={(_, node) => { if (node.data.kind === "area") onToggleArea(node.data.area); else setSelectedId(node.id); }} onMove={handleMove} onMoveEnd={handleMoveEnd} onlyRenderVisibleElements nodesDraggable={false} nodesConnectable={false} elementsSelectable panOnDrag panOnScroll panOnScrollMode={PanOnScrollMode.Free} panOnScrollSpeed={1.15} zoomOnScroll={false} zoomOnPinch zoomOnDoubleClick minZoom={0.1} maxZoom={1.7} defaultViewport={{ x: 620, y: 360, zoom: 0.48 }} proOptions={{ hideAttribution: true }} colorMode="light">
      <Background color="#d4c6db" gap={38} size={1.1} /><Controls showInteractive={false} position="bottom-left" />
      <Panel position="top-left" className="home-atlas-area-filter"><div><strong>Areas</strong><small>{selectedAreas.length ? `${selectedAreas.length} selected` : "All areas"}</small>{selectedAreas.length ? <button onClick={onClearAreas}>Clear</button> : null}</div><div className="home-atlas-area-chips">{areas.map((item) => <button key={item.value} className={selectedAreas.includes(item.value) ? "selected" : ""} onClick={() => onToggleArea(item.value)} title={`${item.count} Principles`}><span>{areaLabel(item.value)}</span><small>{item.count}</small></button>)}</div></Panel>
      {selectedCard ? <Panel position="top-right" className="home-atlas-inspector"><button className="home-atlas-inspector-close" aria-label="Close Principle details" onClick={() => setSelectedId("")}>×</button><small>{areaLabel(cardArea(selectedCard))}</small><strong>{selectedCard.title}</strong><p>{selectedCard.claim}</p><div><span>{selectedCard.supporting_work_count} source paper{selectedCard.supporting_work_count === 1 ? "" : "s"}</span><span>Reliability {selectedCard.reliability_score == null ? "pending" : Math.round(selectedCard.reliability_score)}</span></div></Panel> : <Panel position="top-right" className="home-atlas-count"><strong>{cards.length.toLocaleString()}</strong><span>of {totalCount.toLocaleString()} loaded</span></Panel>}
      <Panel position="bottom-center" className="home-atlas-hint"><span>{density === "full" ? "Claims visible" : density === "title" ? "Titles visible" : density === "dot" ? "Fast node overview" : "Area overview · select an area to enter"}</span>{hasMore && density !== "area" ? <button onClick={onLoadMore} disabled={loadingMore}>{loadingMore ? "Loading next region…" : "Load next region"}</button> : !hasMore ? <em>All matching Principles loaded</em> : null}</Panel>
    </ReactFlow> : null}
  </section>;
}
