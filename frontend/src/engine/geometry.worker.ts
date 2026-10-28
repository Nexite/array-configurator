/// <reference lib="webworker" />
import { PURE_WHEELS, PYODIDE_VERSION } from "./pyVersion";
import { callHandle, installDeps, mountSources, type PyEngine } from "./session";

type Request = { id: number; op: string; payload: unknown };
type PyodideLoader = {
  loadPyodide: (opts: { indexURL: string }) => Promise<PyEngine>;
};

let ready: Promise<PyEngine> | null = null;
let queue: Promise<void> = Promise.resolve();

async function javascriptBase(url: string): Promise<boolean> {
  const response = await fetch(url);
  const type = response.headers.get("content-type") || "";
  await response.arrayBuffer();
  return response.ok && (type.includes("javascript") || type.includes("ecmascript"));
}

async function pyodideIndex(): Promise<string> {
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
  try {
    if (await javascriptBase("/pyodide/pyodide.mjs")) return "/pyodide/";
  } catch {
    /* CDN below */
  }
  return cdn;
}

async function localWheels(): Promise<string[] | undefined> {
  try {
    const response = await fetch("/pyodide/vendor.json");
    const type = response.headers.get("content-type") || "";
    if (!response.ok || !type.includes("json")) return undefined;
    const data = (await response.json()) as { wheels?: string[] };
    const allowed = new Set<string>(PURE_WHEELS);
    const names = (data.wheels || []).filter((name) => allowed.has(name));
    if (!names.length) return undefined;
    return names.map((name) => new URL(`/pyodide/${name}`, self.location.origin).href);
  } catch {
    return undefined;
  }
}

function boot(): Promise<PyEngine> {
  if (!ready) {
    ready = (async () => {
      const indexURL = await pyodideIndex();
      const loader = (await import(/* @vite-ignore */ `${indexURL}pyodide.mjs`)) as PyodideLoader;
      const py = await loader.loadPyodide({ indexURL });
      await installDeps(py, await localWheels());
      mountSources(py);
      return py;
    })();
  }
  return ready;
}

self.onmessage = (event: MessageEvent<Request>) => {
  const { id, op, payload } = event.data;
  queue = queue.then(async () => {
    try {
      const py = await boot();
      if (op === "ping") {
        self.postMessage({ id, result: { ok: true } });
        return;
      }
      self.postMessage({ id, result: callHandle(py, op, payload) });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      self.postMessage({ id, error: message });
    }
  });
};
