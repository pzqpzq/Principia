import { describe, expect, it } from "vitest";
import {
  findingInsightLevel,
  findingResultTab,
  isExecutedSplitRule,
  isLayoutArtifactFinding,
} from "../utils/insightDepth";

describe("finding insight depth", () => {
  it("does not infer scientific classification from persuasive prose", () => {
    expect(
      findingInsightLevel({
        title: "A response reversal defines two operating regimes",
        claim: "The sign reverses across the calibrated boundary.",
        validation_level: "internal_holdout",
        test_ids: ["test:one", "test:two"],
        robustness: ["holdout", "negative control", "alternate model"],
        falsifiers: ["The reversal disappears under matched conditions."],
      }),
    ).toBe("observational");
  });

  it("does not promote an unsupported observation because it sounds scientific", () => {
    expect(
      findingInsightLevel({
        title: "Potential association",
        claim: "Two variables appear related.",
        validation_level: "exploratory",
        robustness: [],
        falsifiers: [],
      }),
    ).toBe("observational");
  });

  it("routes only principle-level findings to Principles", () => {
    expect(findingResultTab({ insight_level: "principle_level" })).toBe(
      "principles",
    );
    expect(findingResultTab({ insight_level: "mechanistic" })).toBe(
      "observations",
    );
  });

  it("rejects prose and failed holdouts from the Rules view", () => {
    expect(
      isExecutedSplitRule({
        record_kind: "data_rule",
        scientific_law: true,
        law_id: "law:fixture",
        expression_latex: "y = 2x + 3",
        test: { passed: true },
      }),
    ).toBe(true);
    expect(
      isExecutedSplitRule({
        record_kind: "data_rule",
        expression_latex: "y = 2x + 3",
        test: { passed: false },
      }),
    ).toBe(false);
    expect(
      isExecutedSplitRule({
        record_kind: "discovery_finding",
        claim: "The variables may be related.",
      }),
    ).toBe(false);
  });

  it("suppresses duplicate-label self-correlations caused by workbook layout", () => {
    expect(
      isLayoutArtifactFinding({
        status: "inconclusive",
        title: "Candidate association: Intensity (arb. units) and Intensity (arb. units)",
      }),
    ).toBe(true);
    expect(
      isLayoutArtifactFinding({
        status: "inconclusive",
        title: "Candidate association: Temperature and Conversion",
      }),
    ).toBe(false);
  });
});
