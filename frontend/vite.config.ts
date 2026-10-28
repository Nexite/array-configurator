import { copyFileSync, createReadStream, existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(root, "..");
const pyodideDir = path.join(root, "node_modules", "pyodide");
const sample = path.join(repo, "samples", "TOPSHELL.DXF");

const MIME: Record<string, string> = {
  ".wasm": "application/wasm",
  ".mjs": "text/javascript",
  ".js": "text/javascript",
  ".json": "application/json",
  ".whl": "application/octet-stream",
  ".zip": "application/zip",
  ".dxf": "application/dxf",
};

function contentType(file: string): string {
  return MIME[path.extname(file).toLowerCase()] || "application/octet-stream";
}

function vendorManifest(): { wheels: string[] } {
  if (!existsSync(pyodideDir)) return { wheels: [] };
  return {
    wheels: readdirSync(pyodideDir).filter((name) => name.startsWith("ezdxf-") || name.startsWith("svgelements-")),
  };
}

function pyodideAssets(): Plugin {
  return {
    name: "pyodide-assets",
    configureServer(server) {
      server.middlewares.use("/pyodide", (req, res, next) => {
        const url = decodeURIComponent((req.url || "/").split("?")[0]);
        const rel = url.replace(/^\/+/, "");
        if (rel === "vendor.json") {
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify(vendorManifest()));
          return;
        }
        if (!rel || rel.includes("..")) return next();
        const file = path.join(pyodideDir, rel);
        if (!file.startsWith(pyodideDir) || !existsSync(file)) return next();
        res.setHeader("Content-Type", contentType(file));
        createReadStream(file).pipe(res);
      });
      server.middlewares.use("/samples/TOPSHELL.DXF", (_req, res) => {
        res.setHeader("Content-Type", "application/dxf");
        createReadStream(sample).pipe(res);
      });
    },
    writeBundle(options) {
      const out = path.resolve(options.dir || path.join(root, "dist"));
      const dest = path.join(out, "pyodide");
      mkdirSync(dest, { recursive: true });
      const keep = new Set([
        "pyodide.mjs",
        "pyodide.asm.mjs",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
        "pyodide-lock.json",
      ]);
      if (existsSync(pyodideDir)) {
        for (const name of readdirSync(pyodideDir)) {
          if (keep.has(name) || name.endsWith(".whl")) {
            copyFileSync(path.join(pyodideDir, name), path.join(dest, name));
          }
        }
      }
      writeFileSync(path.join(dest, "vendor.json"), JSON.stringify(vendorManifest()));
      const sampleDest = path.join(out, "samples");
      mkdirSync(sampleDest, { recursive: true });
      copyFileSync(sample, path.join(sampleDest, "TOPSHELL.DXF"));
    },
  };
}

export default defineConfig({
  plugins: [react(), pyodideAssets()],
  build: { outDir: "dist" },
  server: {
    fs: { allow: [repo] },
  },
  optimizeDeps: { exclude: ["pyodide"] },
  test: {
    environment: "node",
    server: { deps: { external: ["pyodide"] } },
  },
});
