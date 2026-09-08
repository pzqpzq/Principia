import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { components } from "../api/schema";

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    MarkerType: { Arrow: "arrow", ArrowClosed: "arrowclosed" },
    Panel: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
    PanOnScrollMode: { Free: "free" },
    Position: { Top: "top", Right: "right", Bottom: "bottom", Left: "left" },
    ReactFlow: ({ children, nodes, onNodeClick }: { children: React.ReactNode; nodes: Array<{ id: string; data: { card: { title: string } } }>; onNodeClick: (event: unknown, node: { id: string }) => void }) => <div>{nodes.map((node) => <button key={node.id} onClick={() => onNodeClick({}, node)}>Select {node.data.card.title}</button>)}{children}</div>,
    useNodesState: <T,>(initial: T[]) => {
      const [nodes, setNodes] = React.useState(initial);
      return [nodes, setNodes, vi.fn()] as const;
    },
  };
});
import { PrincipleGraph } from "./PrincipleGraph";

type PrincipleCard = components["schemas"]["PrincipleCardResponse"];
type VirtualGeneration = components["schemas"]["VirtualPrincipleGenerationResponse"];

const card = (id: string, title: string): PrincipleCard => ({
  applicability: "Applicable in controlled evaluations.",
  area_labels: ["test-area"],
  boundary_basis: "Recorded boundary",
  claim: `${title} has a testable effect.`,
  claim_type: "mechanism",
  context_relevance: "Test context",
  distinct_neighbor_count: 1,
  evidence_anchor_count: 1,
  evidence_scope: "one_work",
  evidence_status: "checks_passed",
  evidence_types: ["experimental"],
  human_review_status: "reviewed",
  id,
  incoming_contradict_count: 0,
  incoming_support_count: 1,
  influence_score: 62,
  metric_revision: 1,
  related_principles: [],
  reliability_score: 74,
  source: "global",
  supporting_work_count: 1,
  supporting_citation_count: 0,
  citation_data_available: false,
  test_basis: "A controlled test",
  title,
  updated_at: "2026-08-16T00:00:00Z",
  validated_relation_count: 0,
  virtual: false,
});

const cards = [card("prn:test:alpha", "Alpha Principle"), card("prn:test:beta", "Beta Principle")];
const proposal = (index: number) => ({
  area: "test-area",
  assumptions: ["The source mechanisms remain active."],
  claim: `Virtual claim ${index} is falsifiable.`,
  conditions: ["Controlled conditions"],
  contributing_principle_ids: cards.map((item) => item.id),
  derivation_level: "mechanistic_bridge" as const,
  exclusions: ["Uncontrolled settings"],
  falsifier: "The predicted effect is absent.",
  novelty_rationale: "The combination is not stated by either source Principle.",
  novelty_score: 81,
  reliability_rationale: "Both source mechanisms are supported.",
  reliability_score: 72,
  scope_statement: "A bounded test scope.",
  synthesis_summary: "Combines the two selected mechanisms.",
  title: `Virtual Principle ${index}`,
});

const generation: VirtualGeneration = {
  cross_principle_map: ["Alpha + Beta"],
  disclosure: "These are unreviewed hypotheses.",
  items: [1, 2, 3].map((index) => ({ virtual_id: `virtual:${index}`, proposal: proposal(index) })),
  model: "test-model",
  provider: "test-provider",
  trace: { event_id: "trace:test" },
};

const baseProps = {
  cards,
  relations: [],
  selectedId: "",
  onSelectPrinciple: vi.fn(),
  provider: { provider: "test-provider", label: "Test provider", configured: true, defaultModel: "test-model", models: ["test-model"] },
  onOpenSavedVirtualPrinciple: vi.fn(),
  onOpenSavedVirtualLibrary: vi.fn(),
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("PrincipleGraph virtual work guidance", () => {
  it("shows inspectable selections, staged progress, and a recoverable hypothesis tray", async () => {
    let resolveGeneration: (value: VirtualGeneration) => void = () => undefined;
    const pendingGeneration = new Promise<VirtualGeneration>((resolve) => { resolveGeneration = resolve; });
    const save = vi.fn().mockResolvedValue({ candidate_id: "candidate:virtual:1" });
    render(<PrincipleGraph {...baseProps} onAnalyzePotentialRelations={vi.fn()} onGenerateVirtualPrinciples={() => pendingGeneration} onSaveVirtualPrinciple={save} />);

    fireEvent.click(screen.getByRole("button", { name: "Derive Virtual Principles" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Alpha Principle" }));
    expect(screen.getByText("Principle details")).toBeTruthy();
    expect(screen.getByText("Alpha Principle", { selector: "h3" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Select Beta Principle" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Generate 3 Virtual Principles" }));
    expect(screen.getByText("Synthesis in progress")).toBeTruthy();
    expect(screen.getByText("Reading the selected Principles")).toBeTruthy();

    resolveGeneration(generation);
    await waitFor(() => expect(screen.getByText("3 hypotheses from deep synthesis")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Close Virtual Principle studio" }).textContent).toContain("Close");
    fireEvent.click(screen.getAllByRole("button", { name: "Save as local hypothesis" })[0]);
    await waitFor(() => expect(screen.getByRole("button", { name: "Open saved hypothesis" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Close Virtual Principle studio" }));
    fireEvent.click(screen.getByRole("button", { name: /Hypotheses 3/ }));
    expect(screen.getByText("Generated hypothesis batches")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Open Saved hypotheses/ })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Delete virtual hypothesis draft" })).toHaveLength(2);
  });

  it("groups potential connections and lets the user remove them without touching validated relations", async () => {
    const analyze = vi.fn().mockResolvedValue({
      analyzed_pair_count: 1,
      explanation: "One temporary link",
      items: [{ affects_metrics: false, persisted: false, rationale: "Shared mechanism", relation_id: "virtual-edge:1", relation_type: "potential_support", shared_concepts: ["mechanism"], source: cards[0].id, status: "virtual_unvalidated", strength: "moderate", target: cards[1].id }],
      skipped_validated_pair_count: 0,
    });
    render(<PrincipleGraph {...baseProps} onAnalyzePotentialRelations={analyze} onGenerateVirtualPrinciples={vi.fn()} onSaveVirtualPrinciple={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Derive Virtual Connection" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Alpha Principle" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Beta Principle" }));
    fireEvent.click(screen.getByRole("button", { name: "Derive Virtual Connections" }));
    await waitFor(() => expect(screen.getByText("Temporary connection batches")).toBeTruthy());
    expect(screen.getByText("Connection batch 1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delete this virtual connection" }));
    expect(screen.queryByRole("button", { name: /Connections 1/ })).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Validated relations were not changed");
  });
});
