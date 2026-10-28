import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".whl": "application/octet-stream",
  ".zip": "application/zip",
  ".svg": "image/svg+xml",
  ".dxf": "application/dxf",
  ".ico": "image/x-icon",
  ".map": "application/json",
};

export function createStaticApp(rootDir) {
  const root = path.resolve(rootDir);
  return function handle(req, res) {
    const url = decodeURIComponent((req.url || "/").split("?")[0]);
    if (url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end('{"ok":true}');
      return;
    }
    const rel = url.replace(/^\/+/, "");
    if (rel.includes("\0") || rel.split("/").includes("..")) {
      res.writeHead(400);
      res.end("Bad path");
      return;
    }
    let file = path.resolve(root, rel || ".");
    if (file !== root && !file.startsWith(root + path.sep)) {
      res.writeHead(400);
      res.end("Bad path");
      return;
    }
    const missing = !rel || !existsSync(file) || statSync(file).isDirectory();
    if (missing) {
      if (rel && path.extname(rel)) {
        res.writeHead(404);
        res.end("Not found");
        return;
      }
      file = path.join(root, "index.html");
    }
    if (!existsSync(file)) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    const type = MIME[path.extname(file).toLowerCase()] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": type });
    createReadStream(file).pipe(res);
  };
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const root = process.env.STATIC_DIR || path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../dist");
  const port = Number(process.env.PORT || 8080);
  createServer(createStaticApp(root)).listen(port, "0.0.0.0", () => {
    console.log(`listening on ${port}`);
  });
}
