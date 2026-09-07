export type InsightLevel =
  | "observational"
  | "structural"
  | "mechanistic"
  | "principle_level";

export const INSIGHT_LEVELS: InsightLevel[] = [
  "principle_level",
  "mechanistic",
  "structural",
  "observational",
];

export const INSIGHT_LABELS: Record<InsightLevel, string> = {
  principle_level: "Principle-level result",
  mechanistic: "Mechanistic inference",
  structural: "Structural insight",
  observational: "Valuable observation",
};

export const INSIGHT_DESCRIPTIONS: Record<InsightLevel, string> = {
  principle_level: "A scoped, falsifiable rule that may transfer beyond this sample.",
  mechanistic: "Evidence that discriminates how the observed effect may arise.",
  structural: "A regime, boundary, interaction, invariance, or decoupling in the data.",
  observational: "A calibrated, decision-relevant pattern—not an unfiltered correlation.",
};

const text = (value: unknown): string =>
  typeof value === "string" ? value : "";
export function findingInsightLevel(item: Record<string, unknown>): InsightLevel {
  const explicit = text(item.insight_level) as InsightLevel;
  // Scientific classification is persisted by the evidence engine, never
  // reconstructed from wording, titles, or a count of prose claims.
  return INSIGHT_LEVELS.includes(explicit) ? explicit : "observational";
}

export function findingResultTab(
  item: Record<string, unknown>,
): "principles" | "observations" {
  return findingInsightLevel(item) === "principle_level"
    ? "principles"
    : "observations";
}

export function isExecutedSplitRule(item: Record<string, unknown>): boolean {
  const expression = text(item.expression_latex).trim();
  const split =
    item.test !== null && typeof item.test === "object"
      ? (item.test as Record<string, unknown>)
      : {};
  return (
    text(item.record_kind) === "data_rule" &&
    item.scientific_law === true &&
    text(item.law_id).startsWith("law:") &&
    expression.length >= 3 &&
    split.passed === true
  );
}

export function isLayoutArtifactFinding(
  item: Record<string, unknown>,
): boolean {
  if (text(item.status) !== "inconclusive") return false;
  const match = text(item.title).match(
    /^Candidate association:\s*(.*?)\s+and\s+(.+)$/iu,
  );
  if (!match) return false;
  const normalize = (value: string) =>
    value.normalize("NFKC").toLocaleLowerCase().replace(/\s+/g, " ").trim();
  return normalize(match[1]) === normalize(match[2]);
}
