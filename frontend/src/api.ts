import type { Issue, Layout, LayoutParams, LayoutScore, Panel, Region } from "./types";

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const t = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(t.detail || r.statusText);
  }
  return r.json();
}

export async function loadSample(): Promise<{ regions: Region[] }> {
  return j(await fetch("/api/sample/topshell"));
}

export async function importFile(file: File, unit_scale = 1): Promise<{ regions: Region[] }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("unit_scale", String(unit_scale));
  return j(await fetch("/api/import", { method: "POST", body: fd }));
}

export async function pack(regions: Region[], params: LayoutParams): Promise<{ layouts: Layout[] }> {
  return j(await fetch("/api/pack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ regions, params }) }));
}

export async function validate(
  regions: Region[],
  params: LayoutParams,
  panels: Panel[],
): Promise<{ issues: Issue[]; score: LayoutScore }> {
  return j(await fetch("/api/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ regions, params, panels }) }));
}

export async function exportFile(fmt: "svg" | "dxf" | "json", regions: Region[], params: LayoutParams, panels: Panel[]) {
  const r = await fetch(`/api/export/${fmt}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ regions, params, panels }),
  });
  if (!r.ok) throw new Error(await r.text());
  if (fmt === "json") return new Blob([JSON.stringify(await r.json(), null, 2)], { type: "application/json" });
  return r.blob();
}
