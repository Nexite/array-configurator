import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadPyodide } from "pyodide";
import { bestOnAngle, prepareRaster, releaseRaster } from "../src/engine/raster.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const app = path.join(root, "backend", "app");

function sources() {
  const files = {
    "app/__init__.py": "",
    "app/geometry/__init__.py": "",
  };
  for (const name of ["models.py", "serde.py", "client_dispatch.py"]) {
    files[`app/${name}`] = readFileSync(path.join(app, name), "utf8");
  }
  for (const name of readdirSync(path.join(app, "geometry"))) {
    if (!name.endsWith(".py") || name === "__init__.py") continue;
    files[`app/geometry/${name}`] = readFileSync(path.join(app, "geometry", name), "utf8");
  }
  return files;
}

const py = await loadPyodide();
await py.loadPackage(["shapely", "micropip", "fonttools", "pyparsing", "typing-extensions"]);
await py.runPythonAsync(`
import micropip
await micropip.install(["ezdxf==1.4.5", "svgelements==1.9.6"])
`);
py.FS.mkdirTree("/pkg/app/geometry");
for (const [rel, text] of Object.entries(sources())) {
  py.FS.writeFile(`/pkg/${rel}`, text);
}
py.runPython("import sys\nsys.path.insert(0, '/pkg')\n");
py.registerJsModule("raster_js", { bestOnAngle, prepareRaster, releaseRaster });

const svg = readFileSync(path.join(root, "samples", "rectangle.svg"));
py.globals.set("op", "import");
py.globals.set(
  "payload_json",
  JSON.stringify({
    filename: "rectangle.svg",
    data_b64: Buffer.from(svg).toString("base64"),
    unit_scale: 1,
  }),
);
const imported = JSON.parse(
  py.runPython(`
import json
from app.client_dispatch import handle
json.dumps(handle(op, json.loads(payload_json)))
`),
);
if (!imported.regions.some((region) => region.kind === "populate")) {
  throw new Error("rectangle.svg did not produce a populate region");
}

py.globals.set("op", "pack");
py.globals.set(
  "payload_json",
  JSON.stringify({
    regions: imported.regions,
    params: {
      cell_w_mm: 100,
      cell_h_mm: 100,
      cell_gap_mm: 0,
      panel_gap_mm: 0,
      max_wide: 2,
      max_tall: 2,
      target_area_m2: 0.01,
    },
  }),
);
const packed = JSON.parse(
  py.runPython(`
import json
from app.client_dispatch import handle
json.dumps(handle(op, json.loads(payload_json)))
`),
);
const top = packed.layouts[0];
if (!top || top.score.cell_count <= 0) {
  throw new Error("pack produced no cells");
}
console.log(`pyodide packed ${top.score.cell_count} cells in ${packed.layouts.length} layouts`);
