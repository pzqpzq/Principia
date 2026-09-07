export type GraphCamera = { x: number; y: number; angle: number; ratio: number };

export function savedGraphCamera(value: Record<string, unknown>): GraphCamera | undefined {
  // Old releases seeded a world origin as a normalized camera, before any gesture.
  // Genuine saved gestures include angle, even when the user pans to the origin.
  if (!Object.keys(value).length || (value.x === 0 && value.y === 0 && value.ratio === 1 && value.angle === undefined)) return undefined;
  const camera = { x: Number(value.x), y: Number(value.y), angle: Number(value.angle ?? 0), ratio: Number(value.ratio) };
  return Object.values(camera).every(Number.isFinite) && camera.ratio > 0
    ? { ...camera, ratio: Math.max(0.035, Math.min(14, camera.ratio)) } : undefined;
}

export function fittedGraphCamera(points: Array<{x: number; y: number; screenX: number; screenY: number}>, width: number, height: number): GraphCamera | undefined {
  if (!points.length || width <= 0 || height <= 0) return undefined;
  const extent = (key: keyof typeof points[number]) => [Math.min(...points.map(p => p[key])), Math.max(...points.map(p => p[key]))];
  const [left, right] = extent('x'), [bottom, top] = extent('y');
  const [screenLeft, screenRight] = extent('screenX'), [screenTop, screenBottom] = extent('screenY');
  const margin = Math.min(90, width * .24, height * .24);
  return { x: (left + right) / 2, y: (bottom + top) / 2, angle: 0,
    ratio: Math.min(14, Math.max(.9, (screenRight - screenLeft) / (width - 2 * margin), (screenBottom - screenTop) / (height - 2 * margin))) };
}
