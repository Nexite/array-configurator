#!/bin/sh
set -eu
root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$root/frontend"
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi
npm run build
dest="$root/backend/app/static"
rm -rf "$dest"
mkdir -p "$dest"
cp -R dist/. "$dest/"
