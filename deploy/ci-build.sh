#!/usr/bin/env bash
#
# Build the static bundle during the dependency-install phase, but only on a CI
# host.
#
# Why this exists: Workers Builds runs an *optional* Build command and then a
# Deploy command (`npx wrangler deploy` by default). If the Build command field
# is left empty — the default — nothing builds, and `wrangler deploy` fails with
# "the directory specified by the assets.directory field does not exist". The
# install phase, by contrast, always runs (`bun install` triggers `postinstall`),
# so building here guarantees deploy/dist exists no matter what the deploy
# command is.
#
# It is gated on CI so a developer running `npm install` locally is not forced
# through a full production build: install should stay fast. `CI` is set by
# Cloudflare Workers Builds (and by GitHub Actions), and also by this repo's own
# test workflow, where the extra build is a few seconds and does no harm.

set -euo pipefail

if [ "${CI:-}" != "true" ] && [ "${WORKERS_CI:-}" != "1" ]; then
  echo "==> Not a CI host; skipping the demo bundle build"
  exit 0
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT/deploy/build.sh"
