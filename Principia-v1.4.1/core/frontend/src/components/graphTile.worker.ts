type RawItem = {
  principle_id: string;
  record_kind: string;
  origin?: string;
  x: number;
  y: number;
  z_index: number;
  payload: Record<string, unknown>;
};

self.onmessage = (event: MessageEvent<{ items: RawItem[]; includeAreaSupernodes?: boolean }>) => {
  const principles = event.data.items.map((item, index) => {
    const title = typeof item.payload.title === "string" ? item.payload.title : item.principle_id;
    const area = typeof item.payload.area === "string" ? item.payload.area : "interdisciplinary-science";
    const isMeta = item.record_kind === "meta_principle" || item.payload.principle_class === "meta";
    const isArea = item.record_kind === "area";
    return {
      id: item.principle_id,
      x: Number.isFinite(item.x) ? item.x : Math.cos(index * 2.399963) * Math.sqrt(index + 1) * 80,
      y: Number.isFinite(item.y) ? item.y : Math.sin(index * 2.399963) * Math.sqrt(index + 1) * 80,
      rank: Number.isFinite(item.z_index) ? item.z_index : index,
      title,
      area,
      isMeta,
      isArea,
      isVirtual: item.origin === "virtual_principle" || item.payload.virtual === true,
      payload: item.payload,
    };
  });
  const ordinary = principles.filter((item) => !item.isArea);
  const suppliedAreas = principles.filter((item) => item.isArea);
  const groups = new Map<string, typeof ordinary>();
  for (const item of ordinary) groups.set(item.area, [...(groups.get(item.area) ?? []), item]);
  const areas = suppliedAreas.length
    ? suppliedAreas
    : event.data.includeAreaSupernodes
      ? [...groups].map(([area, members], index) => ({
    id: `area:${area}`,
    x: members.reduce((sum, item) => sum + item.x, 0) / members.length,
    y: members.reduce((sum, item) => sum + item.y, 0) / members.length,
    rank: index,
    title: area.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
    area,
    isMeta: false,
    isArea: true,
    isVirtual: false,
    payload: { area, principle_count: members.length, title: area },
  }))
      : [];
  const items = [...ordinary, ...areas];
  self.postMessage({ items });
};

export {};
