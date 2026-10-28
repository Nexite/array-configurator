import { bestOnAngle, prepareRaster, rasterPhases, releaseRaster } from "./raster.mjs";
import { PY_SOURCES } from "./sources";

export type PyEngine = {
  FS: {
    mkdirTree: (path: string) => void;
    writeFile: (path: string, data: string) => void;
  };
  globals: { set: (name: string, value: unknown) => void };
  loadPackage: (names: string | string[]) => Promise<unknown>;
  registerJsModule: (name: string, module: object) => void;
  runPython: (code: string) => unknown;
  runPythonAsync: (code: string) => Promise<unknown>;
};

export async function installDeps(py: PyEngine, wheels?: string[]): Promise<void> {
  await py.loadPackage(["shapely", "micropip", "fonttools", "pyparsing", "typing-extensions"]);
  const specs = wheels?.length ? wheels : ["ezdxf==1.4.5", "svgelements==1.9.6"];
  await py.runPythonAsync(`
import micropip
await micropip.install(${JSON.stringify(specs)})
`);
}

export function registerRaster(py: PyEngine): void {
  py.registerJsModule("raster_js", { bestOnAngle, prepareRaster, rasterPhases, releaseRaster });
}

export function mountSources(py: PyEngine): void {
  py.FS.mkdirTree("/pkg/app/geometry");
  for (const [rel, text] of Object.entries(PY_SOURCES)) {
    py.FS.writeFile(`/pkg/${rel}`, text);
  }
  py.runPython("import sys\nsys.path.insert(0, '/pkg')\n");
}

export function callHandle(py: PyEngine, op: string, payload: unknown): unknown {
  py.globals.set("op", op);
  py.globals.set("payload_json", JSON.stringify(payload));
  const raw = py.runPython(`
import json
from app.client_dispatch import handle
json.dumps(handle(op, json.loads(payload_json)))
`);
  return JSON.parse(String(raw));
}
