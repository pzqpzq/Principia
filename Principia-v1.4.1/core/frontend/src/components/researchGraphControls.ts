export type GraphEdgeLayer = "scientific" | "context" | "virtual";

export type GraphEdgeLayerVisibility = Readonly<Record<GraphEdgeLayer, boolean>>;

const scientificEdgeClasses = new Set([
  "",
  "foundation",
  "scientific",
  "validated",
]);

const virtualEdgeClasses = new Set([
  "virtual",
  "virtual_connection",
  "virtual_relation",
]);

export function graphEdgeLayer(edgeClass: unknown): GraphEdgeLayer {
  const normalized = String(edgeClass ?? "")
    .trim()
    .toLowerCase()
    .replaceAll("-", "_");
  if (virtualEdgeClasses.has(normalized) || normalized.startsWith("virtual_"))
    return "virtual";
  if (scientificEdgeClasses.has(normalized)) return "scientific";
  // Context is the conservative fallback. New or frontend-only edge classes
  // must not look like reviewed scientific relationships by accident.
  return "context";
}

export type SearchableGraphItem = {
  principle_id: string;
  record_kind: string;
  payload: Record<string, unknown>;
};

export type GraphSearchResult<T extends SearchableGraphItem> = {
  item: T;
  title: string;
  area: string;
  score: number;
};

const text = (value: unknown): string =>
  typeof value === "string" ? value.trim() : "";

function normalizedSearchText(value: unknown): string {
  return text(value)
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function rankGraphSearchResults<T extends SearchableGraphItem>(
  items: T[],
  query: string,
  limit = 8,
): GraphSearchResult<T>[] {
  const normalizedQuery = normalizedSearchText(query);
  const tokens = normalizedQuery.split(" ").filter(Boolean);
  if (!tokens.length || limit <= 0) return [];

  return items
    .filter((item) => item.record_kind !== "area")
    .map((item) => {
      const title =
        text(item.payload.title) ||
        text(item.payload.claim).slice(0, 90) ||
        item.principle_id;
      const area =
        text(item.payload.area_display) || text(item.payload.area);
      const titleText = normalizedSearchText(title);
      const claimText = normalizedSearchText(item.payload.claim);
      const argumentText = normalizedSearchText(item.payload.argument);
      const areaText = normalizedSearchText(area);
      const identifierText = normalizedSearchText(item.principle_id);
      const haystack = [
        titleText,
        claimText,
        argumentText,
        areaText,
        identifierText,
      ].join(" ");
      if (!tokens.every((token) => haystack.includes(token))) return null;

      let score = 0;
      if (identifierText === normalizedQuery) score += 140;
      if (titleText === normalizedQuery) score += 120;
      for (const token of tokens) {
        if (titleText.startsWith(token)) score += 30;
        else if (titleText.includes(token)) score += 22;
        if (areaText.includes(token)) score += 12;
        if (claimText.includes(token)) score += 8;
        if (argumentText.includes(token)) score += 5;
        if (identifierText.includes(token)) score += 4;
      }
      return { item, title, area, score };
    })
    .filter((result): result is GraphSearchResult<T> => result !== null)
    .sort(
      (left, right) =>
        right.score - left.score ||
        left.title.localeCompare(right.title) ||
        left.item.principle_id.localeCompare(right.item.principle_id),
    )
    .slice(0, limit);
}
