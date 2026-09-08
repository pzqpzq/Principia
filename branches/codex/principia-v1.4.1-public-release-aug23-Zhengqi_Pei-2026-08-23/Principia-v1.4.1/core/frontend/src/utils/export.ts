export function downloadJson(filename: string, value: unknown) {
  const safeName = filename.replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "") || "principia-record";
  const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${safeName}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
