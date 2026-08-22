export function stableIdentifierHash(value: string): number {
  let output = 2166136261;
  for (let index = 0; index < value.length; index += 1)
    output = Math.imul(output ^ value.charCodeAt(index), 16777619);
  return output >>> 0;
}

const pairKey = (source: string, target: string) =>
  [source, target].sort().join("\0");

export function stableFoundationOrder(
  literatureId: string,
  candidateIds: string[],
): string[] {
  return [...candidateIds].sort(
    (left, right) =>
      stableIdentifierHash(`${literatureId}\0${left}`) -
        stableIdentifierHash(`${literatureId}\0${right}`) ||
      left.localeCompare(right),
  );
}

export function stableScaffoldPairs(
  identifiers: string[],
  blockedPairs: Iterable<string> = [],
): Array<[string, string]> {
  const ordered = [...new Set(identifiers)].sort(
    (left, right) =>
      stableIdentifierHash(left) - stableIdentifierHash(right) ||
      left.localeCompare(right),
  );
  const seen = new Set(blockedPairs);
  const degrees = new Map<string, number>();
  const output: Array<[string, string]> = [];
  const offsets = ordered.length > 12 ? [1, 5] : [1];
  for (const offset of offsets) {
    for (let index = 0; index < ordered.length; index += 1) {
      const source = ordered[index];
      const target = ordered[(index + offset) % ordered.length];
      if (!source || !target || source === target) continue;
      const key = pairKey(source, target);
      if (
        seen.has(key) ||
        (degrees.get(source) ?? 0) >= 3 ||
        (degrees.get(target) ?? 0) >= 3
      )
        continue;
      seen.add(key);
      degrees.set(source, (degrees.get(source) ?? 0) + 1);
      degrees.set(target, (degrees.get(target) ?? 0) + 1);
      output.push([source, target]);
    }
  }
  return output;
}
