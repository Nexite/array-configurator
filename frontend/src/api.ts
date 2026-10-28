import { geometry } from "./engine/client";
import { unsupportedImportMessage } from "./engine/routing";
import type { Issue, Layout, LayoutParams, LayoutScore, Panel, Region } from "./types";

function bytesToB64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export async function importFile(file: File, unit_scale = 1): Promise<{ regions: Region[] }> {
  const unsupported = unsupportedImportMessage(file.name);
  if (unsupported) throw new Error(unsupported);
  const bytes = new Uint8Array(await file.arrayBuffer());
  return geometry("import", { filename: file.name, data_b64: bytesToB64(bytes), unit_scale });
}

export async function pack(regions: Region[], params: LayoutParams): Promise<{ layouts: Layout[] }> {
  return geometry("pack", { regions, params });
}

export async function validate(
  regions: Region[],
  params: LayoutParams,
  panels: Panel[],
): Promise<{ issues: Issue[] }> {
  return geometry("validate", { regions, params, panels });
}

export async function exportFile(fmt: "svg" | "dxf" | "json", regions: Region[], params: LayoutParams, panels: Panel[]) {
  const result = await geometry<
    | { layout: { score: LayoutScore } }
    | { text: string; mime: string }
  >("export", { fmt, regions, params, panels, id: "edit", family: "edit" });
  if (fmt === "json") {
    return new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
  }
  const file = result as { text: string; mime: string };
  return new Blob([file.text], { type: file.mime });
}
