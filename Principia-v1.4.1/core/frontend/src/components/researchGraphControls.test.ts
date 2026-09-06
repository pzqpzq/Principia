import { describe, expect, it } from "vitest";
import {
  graphEdgeLayer,
  rankGraphSearchResults,
  type SearchableGraphItem,
} from "./researchGraphControls";

describe("ResearchGraph relation layers", () => {
  it.each(["validated", "foundation", "scientific", ""])(
    "classifies %j as a scientific link",
    (edgeClass) => expect(graphEdgeLayer(edgeClass)).toBe("scientific"),
  );

  it.each([
    "area_overview",
    "foundation_context",
    "area_context",
    "cluster_context",
    "context_scaffold",
    "shared_evidence",
    "semantic_affinity",
    "unrecognized_future_class",
  ])("classifies %j as map context", (edgeClass) =>
    expect(graphEdgeLayer(edgeClass)).toBe("context"),
  );

  it.each(["virtual", "virtual_connection", "virtual-derived"])(
    "classifies %j as a virtual link",
    (edgeClass) => expect(graphEdgeLayer(edgeClass)).toBe("virtual"),
  );
});

const item = (
  principleId: string,
  title: string,
  claim: string,
  area: string,
  recordKind = "ordinary",
): SearchableGraphItem => ({
  principle_id: principleId,
  record_kind: recordKind,
  payload: { title, claim, area },
});

describe("ResearchGraph in-map search", () => {
  const items = [
    item(
      "prn:biology:feedback",
      "Feedback Control",
      "Negative feedback stabilizes a biological system.",
      "systems-biology",
    ),
    item(
      "prn:physics:feedback",
      "Delayed Oscillation",
      "Feedback delay can create an oscillation.",
      "nonlinear-physics",
    ),
    item("area:biology", "Biology", "", "biology", "area"),
  ];

  it("ranks title matches before claim-only matches and excludes area nodes", () => {
    const results = rankGraphSearchResults(items, "feedback");
    expect(results.map((result) => result.item.principle_id)).toEqual([
      "prn:biology:feedback",
      "prn:physics:feedback",
    ]);
  });

  it("matches multiple normalized tokens across title, claim, area, and id", () => {
    expect(
      rankGraphSearchResults(items, "systems feedback").map(
        (result) => result.item.principle_id,
      ),
    ).toEqual(["prn:biology:feedback"]);
    expect(rankGraphSearchResults(items, "nonlinear-physics")[0]?.area).toBe(
      "nonlinear-physics",
    );
  });

  it("returns no results for blank queries or a non-positive limit", () => {
    expect(rankGraphSearchResults(items, "   ")).toEqual([]);
    expect(rankGraphSearchResults(items, "feedback", 0)).toEqual([]);
  });
});
