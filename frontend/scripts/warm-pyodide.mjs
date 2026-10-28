import { createWriteStream, existsSync, readFileSync } from "node:fs";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dest = path.join(root, "node_modules", "pyodide");
const lock = JSON.parse(readFileSync(path.join(dest, "pyodide-lock.json"), "utf8"));
const version = JSON.parse(readFileSync(path.join(dest, "package.json"), "utf8")).version;
const cdn = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;

function walk(name, seen) {
  if (seen.has(name)) return;
  const pkg = lock.packages[name];
  if (!pkg) throw new Error(`Pyodide lock has no package ${name}`);
  seen.add(name);
  for (const dep of pkg.depends || []) walk(dep, seen);
}

async function download(url, file) {
  if (existsSync(file)) return;
  const response = await fetch(url);
  if (!response.ok || !response.body) throw new Error(`Failed to download ${url}: ${response.status}`);
  await pipeline(Readable.fromWeb(response.body), createWriteStream(file));
  console.log("saved", path.basename(file));
}

const needed = new Set();
for (const name of ["shapely", "micropip", "fonttools", "pyparsing", "typing-extensions"]) walk(name, needed);
for (const name of needed) {
  const file = lock.packages[name].file_name;
  await download(cdn + file, path.join(dest, file));
}

const pure = [
  ["ezdxf", "1.4.5", (name) => name.endsWith("py3-none-any.whl")],
  ["svgelements", "1.9.6", (name) => name.endsWith(".whl")],
];
for (const [pkg, ver, pred] of pure) {
  const meta = await (await fetch(`https://pypi.org/pypi/${pkg}/${ver}/json`)).json();
  const file = meta.urls.find((item) => item.packagetype === "bdist_wheel" && pred(item.filename));
  if (!file) throw new Error(`No wheel for ${pkg} ${ver}`);
  await download(file.url, path.join(dest, file.filename));
}

console.log("pyodide assets ready");
