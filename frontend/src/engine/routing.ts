const DROPPED_EXTS = new Set([".pdf", ".ai", ".eps", ".dwg"]);

const DROPPED_MESSAGE = "PDF, AI, EPS, and DWG are not supported. Use DXF, SVG, or HPGL.";

/** Returns an error message for formats this app does not parse. */
export function unsupportedImportMessage(filename: string): string | null {
  const dot = filename.lastIndexOf(".");
  const ext = (dot >= 0 ? filename.slice(dot) : "").toLowerCase();
  return DROPPED_EXTS.has(ext) ? DROPPED_MESSAGE : null;
}
