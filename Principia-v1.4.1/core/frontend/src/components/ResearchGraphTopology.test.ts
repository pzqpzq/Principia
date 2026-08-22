import { describe, expect, it } from "vitest";
import {
  stableFoundationOrder,
  stableScaffoldPairs,
} from "./researchGraphTopology";

describe("ResearchGraph stable topology", () => {
  it("keeps foundation choices independent of dragged coordinates", () => {
    const beforeDrag = [
      { id: "meta:physics:symmetry", x: 10, y: 10 },
      { id: "meta:physics:conservation", x: 400, y: -50 },
      { id: "meta:physics:causality", x: -220, y: 180 },
    ];
    const afterDrag = [
      { ...beforeDrag[0], x: 9_000, y: -8_000 },
      { ...beforeDrag[1], x: -7_000, y: 6_000 },
      { ...beforeDrag[2], x: 3, y: 4 },
    ];
    expect(
      stableFoundationOrder(
        "prn:physics:test",
        beforeDrag.map((item) => item.id),
      ),
    ).toEqual(
      stableFoundationOrder(
        "prn:physics:test",
        afterDrag.map((item) => item.id),
      ),
    );
  });

  it("builds the same bounded scaffold after arbitrary node movement", () => {
    const identifiers = Array.from({ length: 24 }, (_, index) =>
      `prn:science:${index.toString().padStart(2, "0")}`,
    );
    const blocked = new Set([
      [identifiers[0], identifiers[1]].sort().join("\0"),
    ]);
    const before = stableScaffoldPairs(identifiers, blocked);
    const after = stableScaffoldPairs([...identifiers].reverse(), blocked);
    expect(after).toEqual(before);
    const degree = new Map<string, number>();
    for (const [source, target] of before) {
      degree.set(source, (degree.get(source) ?? 0) + 1);
      degree.set(target, (degree.get(target) ?? 0) + 1);
    }
    expect(Math.max(...degree.values())).toBeLessThanOrEqual(3);
  });
});
