/** Display precision never changes persisted values or executable coefficients. */
export function scientificNumber(value: number, exact = false): string {
  if (!Number.isFinite(value)) return String(value);
  if (exact) return String(value);
  if (value === 0) return "0";
  if (Number.isInteger(value) && Math.abs(value) < 1e7) return value.toLocaleString("en-US");
  if (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e7) {
    return value.toExponential(3).replace(/\.?(0+)(?=e)/, "").replace("e+", "e");
  }
  return String(Number(value.toPrecision(4)));
}

/** Round long decimal measurements in prose/math, preserving identifiers/paths. */
export function conciseMeasurements(value: string): string {
  return value.replace(/(?<![\w/.:-])-?\d+\.\d{6,}(?:[eE][+-]?\d+)?(?![\w/.:-])/g,
    token => scientificNumber(Number(token)));
}
