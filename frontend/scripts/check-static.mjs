import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { once } from "node:events";
import assert from "node:assert/strict";
import { createStaticApp } from "./static-server.mjs";

const root = mkdtempSync(path.join(tmpdir(), "array-static-"));
writeFileSync(path.join(root, "index.html"), "<html><title>Array Configurator</title></html>");
writeFileSync(path.join(root, "pyodide.mjs"), "export {}\n");
const server = createServer(createStaticApp(root));
server.listen(0, "127.0.0.1");
await once(server, "listening");
const port = server.address().port;

try {
  const health = await fetch(`http://127.0.0.1:${port}/health`);
  assert.equal(health.status, 200);
  assert.equal(await health.text(), '{"ok":true}');

  const home = await fetch(`http://127.0.0.1:${port}/`);
  assert.equal(home.status, 200);
  assert.match(await home.text(), /Array Configurator/);

  const script = await fetch(`http://127.0.0.1:${port}/pyodide.mjs`);
  assert.equal(script.headers.get("content-type"), "text/javascript");

  const missing = await fetch(`http://127.0.0.1:${port}/missing.wasm`);
  assert.equal(missing.status, 404);

  const escape = await new Promise((resolve) => {
    const res = {
      writeHead(status) {
        this.statusCode = status;
      },
      end() {
        resolve(this.statusCode);
      },
    };
    createStaticApp(root)({ url: "/%2e%2e/package.json" }, res);
  });
  assert.equal(escape, 400);
} finally {
  server.close();
  rmSync(root, { recursive: true, force: true });
}
