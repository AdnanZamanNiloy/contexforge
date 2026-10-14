# Deploy — Cloudflare Pages (static demo)

One Cloudflare Pages project serves three things from a single origin:

| Path | What it is |
|---|---|
| `/` | The landing page, plus the demo workspace it links into |
| `/docs` | The documentation site |
| `/docs/*` | Deeper docs routes |

There is **no backend**. Cloudflare Pages hosts static files only — no FastAPI
process, no SQLite, no model provider. The workspace runs against a mock
compiled into the bundle, so a visitor can open a project, read a captured
conversation, ask a question and watch a grounded answer stream in, exactly as
against the real server.

## Layout

```
deploy/
├── build.sh          builds the frontend + docs into deploy/dist/
├── _redirects        routing (docs shell vs app shell)
├── _headers          cache + security headers
├── README.md         this file
├── demo/
│   ├── seed.js       the captured data (projects, sources, conversations)
│   └── mock.js       the stand-in backend (replays the SSE wire format)
└── dist/             build output (git-ignored)
```

Alongside it, at the repository root:

- **`package.json`** — a shim so Cloudflare's build runner installs the
  frontend and docs dependencies and runs `deploy/build.sh`.
- **`wrangler.jsonc`** — static-asset config pointing at `deploy/dist`.

`deploy/demo/` is imported by `frontend/src/services/api.js`. It lives outside
`frontend/` because it is a deployment artefact, not app code — the live app
never loads it unless `VITE_DEMO_MODE=true`.

## What is real and what is mocked

**Real.** Every project, source, question and answer shown is captured verbatim
from a running instance. The answer text, the citations, the source list and the
per-stage latency shape are the real ones.

**Mocked.** Three things, all stated plainly in the UI:

1. **The backend.** There is none. `deploy/demo/mock.js` answers in-process and
   emits the same Server-Sent Events the server does, so `useChat`, `ChatBox`,
   the confidence meter and the latency readout need no demo-specific code.
2. **Confidence.** The captured runs scored `0.15` ("Weak") because the questions
   were broad. The seed sets a confident `0.86–0.93` band so the meter shows a
   well-grounded answer instead of reading as broken. This is the one value
   deliberately changed from the capture.
3. **Ingestion, notes, mind maps and Studio.** Disabled, with an honest message.
   A static host cannot fetch, chunk, embed or index, so pretending otherwise
   would be worse than saying so.

## Matching a typed question

A visitor's question is matched against the captured conversations by keyword,
biased toward whichever seed answer came from the sources they have selected.
Anything unrecognised returns a canned low-confidence answer that names the
demo's limits rather than faking a retrieval.

## Build

```bash
bash deploy/build.sh
```

Produces `deploy/dist/`:

- the frontend built with `VITE_DEMO_MODE=true` at the root,
- the docs built with `VITE_DOCS_BASE=/docs/` under `docs/`,
- `_redirects` and `_headers` copied alongside.

## Deploy

The repo carries a root `package.json` and a `wrangler.jsonc`, so the
Cloudflare build runner installs the frontend and docs dependencies at the root
and serves the built bundle from `deploy/dist`.

### Connect the repository (recommended)

Create a Worker from this repository. Workers Builds runs an optional **Build
command**, then a **Deploy command** (`npx wrangler deploy` by default). Set
these in **Settings → Build**:

| Setting | Value |
|---|---|
| Build command | *(leave empty)* |
| Deploy command | `npm run deploy` |
| Environment variable | `NODE_VERSION=22` |

`npm run deploy` builds the bundle into `deploy/dist` and then runs
`wrangler deploy`, which reads `wrangler.jsonc`. Use this single-script form
rather than a separate build command: the deploy command runs unconditionally,
so it is the one setting that cannot be left blank and silently produce an empty
`assets.directory` (which fails with *"the directory specified by the
assets.directory field ... does not exist"*).

The same build can be run on its own with **Build command** `npm run build` and
**Deploy command** `npx wrangler deploy`; either arrangement works as long as
the build runs before the deploy.

### Build locally, upload

```bash
npm run build                  # -> deploy/dist
npx wrangler deploy            # reads wrangler.jsonc -> deploy/dist
```

### Why a root package.json

Cloudflare's build runner looks for a `package.json` at the repository root. The
app lives in `frontend/` and the docs in `docs-site/`, so the root file is a thin
shim: its `postinstall` installs both, and its `build` / `deploy` scripts drive
the bundle. Without it the runner has nothing to install and the build produces a
blank page.

## Why one project

Cloudflare Pages is static-only and a free project is a single origin. Serving
the landing page, the docs and the demo together keeps the Docs link
same-origin, so navigation is instant and the browser back button works. Splitting
them across projects would put the docs on a second hostname and reopen the
new-tab, no-back-history problem this deploy was built to avoid.
