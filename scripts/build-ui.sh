#!/bin/sh
set -eu
root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$root/frontend"
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi
node scripts/warm-pyodide.mjs
npm run build
