#!/usr/bin/env bash
#
# Build the static demo bundle for Cloudflare (Workers static assets or Pages).
# Run from the repo root, or via the root package.json:
#
#     npm run build
#
# Output:
#
#   deploy/dist/            landing page + demo workspace (the frontend build)
#   deploy/dist/docs/       the documentation site, mounted under /docs
#   deploy/dist/_headers    cache + security headers
#
# deploy/worker.js routes between the two SPAs; there is no _redirects file
# (its shell-rewrite rules loop, and Cloudflare rejects them). See worker.js.
#
# One project serves all three, so the landing page, the docs and the demo share
# one origin — the Docs link stays same-origin and the browser back button works.
#
# No backend is deployed. The demo workspace runs against the mock in
# `deploy/demo/mock.js`, which is compiled into the frontend bundle and replays
# captured conversations. See deploy/README.md.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/deploy/dist"

echo "==> Cleaning $DIST"
rm -rf "$DIST"
mkdir -p "$DIST"

echo "==> Building the demo frontend (landing + workspace) with VITE_DEMO_MODE=true"
cd "$ROOT/frontend"
[ -d node_modules ] || (npm ci || npm install)
VITE_DEMO_MODE=true npm run build -- --outDir "$DIST" --emptyOutDir

echo "==> Building the docs site with base=/docs/"
cd "$ROOT/docs-site"
[ -d node_modules ] || (npm ci || npm install)
VITE_DOCS_BASE=/docs/ npm run build -- --outDir "$DIST/docs" --emptyOutDir

echo "==> Writing the header control file"
cp "$ROOT/deploy/_headers" "$DIST/_headers"

echo "==> Done. Output in deploy/dist:"
find "$DIST" -maxdepth 1 -mindepth 1 | sort
